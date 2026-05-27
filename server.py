# -*- coding: utf-8 -*-
import sys
import logging
import time
import os

print(f"[调试] 当前工作目录: {os.getcwd()}", flush=True)
print(f"[调试] 服务器目录: {os.path.dirname(os.path.abspath(__file__))}", flush=True)

# 确保 stdout/stderr 使用 UTF-8 编码
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('game_engine.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

def log_to_console_and_file(message):
    """记录日志到控制台和文件"""
    logger.info(message)

from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
from api.game_api import (
    init_game,
    get_game_state,
    night_step,
    night_step_stream,
    day_step,
    day_step_stream,
    vote_step,
    vote_step_stream,
    get_history,
    check_win,
    get_role_config,
    set_werewolf_target,
    execute_wolf_action,
)
from api.exceptions import GameNotFoundError, InvalidPhaseError, InvalidPlayerError, GameAlreadyOverError
import os

app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app, resources={r"/api/*": {"origins": "*"}})


@app.route('/')
def index():
    return send_from_directory('frontend', 'index.html')


@app.route('/api/test', methods=['GET'])
def api_test():
    """测试API是否正常工作"""
    return jsonify({'status': 'ok', 'message': 'API works'})


@app.route('/api/game/role-config/<int:num_players>', methods=['GET'])
def api_get_role_config(num_players):
    """获取指定人数的角色配置"""
    try:
        roles = get_role_config(num_players)
        return jsonify({
            "num_players": num_players,
            "roles": roles,
            "role_count": {
                "狼人": roles.count("狼人"),
                "预言家": roles.count("预言家"),
                "女巫": roles.count("女巫"),
                "村民": roles.count("村民")
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 400


@app.route('/api/game/init', methods=['POST'])
def api_init_game():
    data = request.json or {}
    num_players = data.get('num_players', 4)
    human_player_id = data.get('human_player_id', 0)
    human_role = data.get('human_role', None)
    try:
        logger.info(f"[API] 收到游戏初始化请求: {num_players}名玩家, 人类玩家ID: {human_player_id}, 选择角色: {human_role}")
        state = init_game(num_players, human_player_id, human_role)
        logger.info(f"[API] 游戏创建成功: {state.game_id}, 玩家角色: {state.player_roles}")
        return jsonify(state.to_dict())
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 400


@app.route('/api/game/state/<game_id>', methods=['GET'])
def api_get_state(game_id):
    try:
        state = get_game_state(game_id)
        return jsonify(state.to_dict())
    except GameNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 400


@app.route('/api/game/werewolf-target', methods=['POST'])
def api_set_werewolf_target():
    """设置狼人击杀目标（用于分步执行夜晚阶段）"""
    data = request.json
    try:
        result = set_werewolf_target(
            data['game_id'],
            data.get('target'),
        )
        return jsonify(result)
    except (GameNotFoundError, InvalidPhaseError, GameAlreadyOverError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/game/execute-wolf-action', methods=['POST'])
def api_execute_wolf_action():
    """让狼人AI自动执行击杀行动"""
    data = request.json
    try:
        result = execute_wolf_action(data['game_id'])
        return jsonify(result)
    except (GameNotFoundError, InvalidPhaseError, InvalidPlayerError, GameAlreadyOverError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/game/night', methods=['POST'])
def api_night_step():
    data = request.json
    try:
        result = night_step(
            data['game_id'],
            user_werewolf_target=data.get('user_werewolf_target'),
            user_seer_target=data.get('user_seer_target'),
            user_witch_save=data.get('user_witch_save', False),
            user_witch_poison=data.get('user_witch_poison'),
        )
        return jsonify(result.to_dict())
    except (GameNotFoundError, InvalidPhaseError, GameAlreadyOverError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/game/night-stream', methods=['POST'])
def api_night_step_stream():
    """流式夜晚阶段 - SSE"""
    data = request.json
    game_id = data.get('game_id')

    try:
        logger.info(f"[API] 收到流式夜晚请求: game={game_id}")

        def generate():
            try:
                for event in night_step_stream(
                    game_id,
                    user_werewolf_target=data.get('user_werewolf_target'),
                    user_seer_target=data.get('user_seer_target'),
                    user_witch_save=data.get('user_witch_save', False),
                    user_witch_poison=data.get('user_witch_poison'),
                ):
                    json_str = __import__('json').dumps(event, ensure_ascii=False)
                    yield f"data: {json_str}\n\n"
            except GameAlreadyOverError:
                yield "data: " + __import__('json').dumps({"type": "error", "message": "游戏已结束"}, ensure_ascii=False) + "\n\n"
            except InvalidPhaseError:
                yield "data: " + __import__('json').dumps({"type": "error", "message": "当前不是夜晚阶段"}, ensure_ascii=False) + "\n\n"
            except Exception as e:
                import traceback
                traceback.print_exc()
                yield "data: " + __import__('json').dumps({"type": "error", "message": str(e)}, ensure_ascii=False) + "\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/game/day', methods=['POST'])
def api_day_step():
    data = request.json
    try:
        result = day_step(data['game_id'], data['user_speak'])
        return jsonify(result.to_dict())
    except (GameNotFoundError, InvalidPhaseError, GameAlreadyOverError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/game/day-stream', methods=['POST'])
def api_day_step_stream():
    """流式白天发言 - SSE"""
    data = request.json
    game_id = data.get('game_id')
    user_speak = data.get('user_speak', '')

    try:
        logger.info(f"[API] 收到流式发言请求: game={game_id}, speak_len={len(user_speak)}")

        def generate():
            try:
                for event in day_step_stream(game_id, user_speak):
                    json_str = __import__('json').dumps(event, ensure_ascii=False)
                    yield f"data: {json_str}\n\n"
            except GameAlreadyOverError:
                yield "data: " + __import__('json').dumps({"type": "error", "message": "游戏已结束"}, ensure_ascii=False) + "\n\n"
            except InvalidPhaseError:
                yield "data: " + __import__('json').dumps({"type": "error", "message": "当前不是白天阶段"}, ensure_ascii=False) + "\n\n"
            except Exception as e:
                import traceback
                traceback.print_exc()
                yield "data: " + __import__('json').dumps({"type": "error", "message": str(e)}, ensure_ascii=False) + "\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/game/vote', methods=['POST'])
def api_vote_step():
    data = request.json
    try:
        result = vote_step(data['game_id'], data['user_vote'])
        return jsonify(result.to_dict())
    except (GameNotFoundError, InvalidPhaseError, GameAlreadyOverError, InvalidPlayerError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/game/vote-stream', methods=['POST'])
def api_vote_step_stream():
    """流式投票 — SSE，并行 AI 投票，实时推送进度"""
    data = request.json
    game_id = data.get('game_id')
    user_vote = data.get('user_vote')

    try:
        logger.info(f"[API] 收到流式投票请求: game={game_id}, vote={user_vote}")

        def generate():
            try:
                for event in vote_step_stream(game_id, user_vote):
                    json_str = __import__('json').dumps(event, ensure_ascii=False)
                    yield f"data: {json_str}\n\n"
            except GameAlreadyOverError:
                yield "data: " + __import__('json').dumps({"type": "error", "message": "游戏已结束"}, ensure_ascii=False) + "\n\n"
            except InvalidPhaseError:
                yield "data: " + __import__('json').dumps({"type": "error", "message": "当前不是投票阶段"}, ensure_ascii=False) + "\n\n"
            except Exception as e:
                import traceback
                traceback.print_exc()
                yield "data: " + __import__('json').dumps({"type": "error", "message": str(e)}, ensure_ascii=False) + "\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/game/history/<game_id>', methods=['GET'])
def api_get_history(game_id):
    try:
        history = get_history(game_id)
        return jsonify([e.to_dict() for e in history])
    except GameNotFoundError as e:
        return jsonify({'error': str(e)}), 404


@app.route('/api/game/winner/<game_id>', methods=['GET'])
def api_check_win(game_id):
    try:
        winner = check_win(game_id)
        return jsonify({'winner': winner})
    except GameNotFoundError as e:
        return jsonify({'error': str(e)}), 404


if __name__ == '__main__':
    os.makedirs('frontend', exist_ok=True)
    port = 8080
    print(f"[服务器] 正在启动狼人杀游戏服务器...", flush=True)
    print(f"[服务器] 访问 http://localhost:{port} 开始游戏", flush=True)
    print(f"[服务器] 也可以通过 http://127.0.0.1:{port} 访问", flush=True)
    app.run(debug=False, host='0.0.0.0', port=port, threaded=False, use_reloader=False)
