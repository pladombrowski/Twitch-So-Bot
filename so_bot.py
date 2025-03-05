import traceback
import requests
import random

from flask import Flask, request, jsonify, render_template_string, redirect

from flask_cors import CORS
import time
from obswebsocket import obsws, requests as obsrequests
import re
import yaml
import asyncio
from twitchio.ext import commands
import threading
import webbrowser

app = Flask(__name__)
CORS(app)

CONFIG_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Configuração do Bot Twitch</title>
    <style>
        :root {
            --bg: #282a36;
            --fg: #f8f8f2;
            --purple: #bd93f9;
            --pink: #ff79c6;
            --cyan: #8be9fd;
            --green: #50fa7b;
            --orange: #ffb86c;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Segoe UI', sans-serif;
            background: var(--bg);
            color: var(--fg);
            line-height: 1.6;
            padding: 20px;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
            background: rgba(40, 42, 54, 0.9);
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 0 20px rgba(0, 0, 0, 0.3);
        }

        h1 {
            color: var(--purple);
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5em;
        }

        .form-section {
            margin-bottom: 30px;
            padding: 20px;
            background: rgba(68, 71, 90, 0.3);
            border-radius: 8px;
        }

        h2 {
            color: var(--cyan);
            margin-bottom: 15px;
            font-size: 1.4em;
        }

        .form-group {
            margin-bottom: 20px;
        }

        label {
            display: block;
            margin-bottom: 8px;
            color: var(--green);
            font-weight: 500;
        }

        input {
            width: 100%;
            padding: 12px;
            background: rgba(98, 114, 164, 0.2);
            border: 2px solid var(--purple);
            border-radius: 5px;
            color: var(--fg);
            font-size: 16px;
            transition: all 0.3s ease;
        }

        input:focus {
            outline: none;
            border-color: var(--cyan);
            background: rgba(98, 114, 164, 0.3);
        }

        button {
            background: var(--purple);
            color: var(--bg);
            border: none;
            padding: 15px 30px;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.3s ease;
            display: block;
            width: 100%;
            font-weight: bold;
            text-transform: uppercase;
        }

        button:hover {
            background: var(--cyan);
            color: var(--bg);
        }

        .alert {
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 5px;
            text-align: center;
        }

        .success {
            background: rgba(80, 250, 123, 0.2);
            border: 2px solid var(--green);
        }

        .error {
            background: rgba(255, 121, 198, 0.2);
            border: 2px solid var(--pink);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Configuração do Bot Twitch</h1>

        {% if message %}
        <div class="alert {{ message_type }}">{{ message }}</div>
        {% endif %}

        <form method="post">
            <div class="form-section">
                <h2>Configurações da Twitch</h2>

                <div class="form-group">
                    <label for="twitch_username">Nome de Usuário Twitch:</label>
                    <input type="text" id="twitch_username" name="TWITCH_USERNAME" 
                           value="{{ config.TWITCH_USERNAME }}" required>
                </div>

                <div class="form-group">
                    <label for="client_id">Client ID:</label>
                    <input type="text" id="client_id" name="TWITCH_CLIENT_ID" 
                           value="{{ config.TWITCH_CLIENT_ID }}" required>
                </div>

                <div class="form-group">
                    <label for="client_secret">Client Secret:</label>
                    <input type="text" id="client_secret" name="TWITCH_CLIENT_SECRET" 
                           value="{{ config.TWITCH_CLIENT_SECRET }}" required>
                </div>
                
                <div class="form-group">
                    <label for="client_secret">Tempo máximo dos vídeos em segundos:</label>
                    <input type="number" id="max_video_time" name="MAX_VIDEO_TIME" 
                           value="{{ config.MAX_VIDEO_TIME }}" required>
                </div>
            </div>

            <div class="form-section">
                <h2>Configurações do OBS</h2>

                <div class="form-group">
                    <label for="obs_host">Host OBS:</label>
                    <input type="text" id="obs_host" name="OBS_HOST" 
                           value="{{ config.OBS_HOST }}" required>
                </div>

                <div class="form-group">
                    <label for="obs_port">Porta OBS:</label>
                    <input type="number" id="obs_port" name="OBS_PORT" 
                           value="{{ config.OBS_PORT }}" required>
                </div>

                <div class="form-group">
                    <label for="obs_password">Senha do OBS WebSocket:</label>
                    <input type="text" id="obs_password" name="OBS_PASSWORD" 
                           value="{{ config.OBS_PASSWORD }}" required>
                </div>
            </div>
            <div class="form-section">
                <h2>Usuários Autorizados</h2>
                <div class="form-group">
                    <label for="authorized_users">Nomes de usuário permitidos (separados por vírgula):</label>
                        <input type="text" id="authorized_users" name="AUTHORIZED_USERS" 
                            value="{{ ','.join(config.AUTHORIZED_USERS) }}" 
                            placeholder="Ex: seuusuario,moderador1,moderador2">
                </div>
                <small>Adicione os nomes exatos dos usuários do Twitch que podem usar comandos</small>
            </div>
            <button type="submit">Salvar Configurações</button>
        </form>
    </div>
</body>
</html>
"""

# Evento para controle de autenticação
auth_complete_event = threading.Event()

global config

global selected_video_duration

restart_bot_event = threading.Event()
app_should_restart = threading.Event()
global_config = None


def load_config():
    global global_config
    try:
        with open("config.yaml", "r") as file:
            global_config = yaml.safe_load(file)
    except FileNotFoundError:
        global_config = {
            'TWITCH_CLIENT_ID': 'your_client_id',
            'TWITCH_CLIENT_SECRET': 'your_client_secret',
            'OBS_HOST': 'localhost',
            'OBS_PORT': 4455,
            'OBS_PASSWORD': 'obs_websocket_password',
            'TWITCH_USERNAME': 'your_username',
            'TWITCH_REDIRECT_URI': 'http://localhost:5000/auth/callback'
        }


def save_config():
    with open("config.yaml", "w") as file:
        yaml.dump(global_config, file)


def load_tokens():
    try:
        with open("tokens.yaml", "r") as f:
            tokens = yaml.safe_load(f)
            if tokens and 'access_token' in tokens and 'refresh_token' in tokens:
                return tokens
    except FileNotFoundError:
        pass
    return None


def save_tokens(access_token, refresh_token, expires_in):
    tokens = {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'expires_at': time.time() + expires_in
    }
    with open("tokens.yaml", "w") as f:
        yaml.dump(tokens, f)


def refresh_tokens():
    tokens = load_tokens()
    if not tokens or 'refresh_token' not in tokens:
        return False

    try:
        response = requests.post(
            'https://id.twitch.tv/oauth2/token',
            params={
                'client_id': global_config['TWITCH_CLIENT_ID'],
                'client_secret': global_config['TWITCH_CLIENT_SECRET'],
                'grant_type': 'refresh_token',
                'refresh_token': tokens['refresh_token']
            }
        )
        response.raise_for_status()

        token_data = response.json()
        save_tokens(
            token_data['access_token'],
            token_data.get('refresh_token', tokens['refresh_token']),
            token_data['expires_in']
        )
        return True
    except Exception as e:
        print(f"Erro ao renovar token: {str(e)}")
        return False


def get_valid_token():
    tokens = load_tokens()

    if tokens and tokens['expires_at'] > time.time() + 60:  # 1 minuto de margem
        return tokens['access_token']

    if tokens and refresh_tokens():
        return load_tokens()['access_token']

    return None


class TwitchBot(commands.Bot):
    def __init__(self):
        self.token = get_valid_token()
        super().__init__(
            token=self.token,
            client_id=global_config['TWITCH_CLIENT_ID'],
            nick=global_config['TWITCH_USERNAME'],
            prefix='!',
            initial_channels=[global_config['TWITCH_USERNAME'].lower()]
        )

    async def monitor_restart(self):
        while not restart_bot_event.is_set():
            await asyncio.sleep(1)
        await self.close()

    async def start(self):
        self.loop.create_task(self.monitor_restart())
        await super().start()

    async def event_ready(self):
        print(f'Bot conectado como {self.nick}')

    async def event_error(self, error, data=None):
        if 'Authentication failed' in str(error):
            print("Token inválido, tentando renovar...")
            if refresh_tokens():
                self.token = get_valid_token()
                await self.close()
                self._connection._token = self.token
                await self.connect()
            else:
                print("Falha na renovação do token. Requer reautenticação.")
                auth_complete_event.clear()
                start_auth_flow()

    async def event_message(self, message):
        if message.echo:
            return
        await self.handle_commands(message)

    @commands.command(name='so')
    async def shoutout_command(self, ctx, channel_name: str = None):
        authorized_users = [user.lower() for user in global_config['AUTHORIZED_USERS']]
        is_authorized = (
                ctx.author.name.lower() in authorized_users or
                ctx.author.is_mod or
                ctx.author.name.lower() == global_config['TWITCH_USERNAME'].lower()
        )

        if not is_authorized:
            await ctx.send("❌ Você não tem permissão para usar este comando!")
            return

        if not channel_name:
            await ctx.send("Formato correto: !so <nome_do_canal>")
            return

        if not re.match(r'^[a-zA-Z0-9_]{4,25}$', channel_name):
            await ctx.send("Nome de canal inválido")
            return

        try:
            response = requests.post(
                'http://localhost:5000/play',
                json={'channel': channel_name},
                timeout=35
            )

            if response.status_code == 200:
                await ctx.send(f"🎥 Reproduzindo conteúdo de {channel_name}!")
                remove_browser_source(selected_video_duration)
            else:
                error_msg = response.json().get('error', 'Erro desconhecido')
                await ctx.send(f"❌ Erro: {error_msg}")

        except Exception as e:
            print(f"Erro na requisição: {str(e)}")
            await ctx.send("🔧 Erro interno ao processar o pedido")


def start_auth_flow():
    params = {
        'client_id': global_config['TWITCH_CLIENT_ID'],
        'redirect_uri': global_config['TWITCH_REDIRECT_URI'],
        'response_type': 'code',
        'scope': 'chat:read chat:edit'
    }
    auth_url = requests.Request('GET', 'https://id.twitch.tv/oauth2/authorize', params=params).prepare().url
    print(f"Por favor, autorize o aplicativo: {auth_url}")
    webbrowser.open(auth_url)


@app.route('/auth/callback')
def auth_callback():
    code = request.args.get('code')
    if not code:
        return jsonify({'error': 'Código de autorização ausente'}), 400

    try:
        response = requests.post(
            'https://id.twitch.tv/oauth2/token',
            params={
                'client_id': global_config['TWITCH_CLIENT_ID'],
                'client_secret': global_config['TWITCH_CLIENT_SECRET'],
                'code': code,
                'grant_type': 'authorization_code',
                'redirect_uri': global_config['TWITCH_REDIRECT_URI']
            }
        )
        response.raise_for_status()

        token_data = response.json()
        save_tokens(
            token_data['access_token'],
            token_data['refresh_token'],
            token_data['expires_in']
        )
        auth_complete_event.set()
        return "Autenticação bem-sucedida! Você pode fechar esta janela."
    except Exception as e:
        print(f"Erro na autenticação: {str(e)}")
        return jsonify({'error': 'Falha na autenticação'}), 500


def interval_string_to_seconds(input_str: str) -> int:
    SUFFIX_MAP = {
        'y': 'y',
        'year': 'y',
        'years': 'y',
        'w': 'w',
        'week': 'w',
        'weeks': 'w',
        'd': 'd',
        'day': 'd',
        'days': 'd',
        'h': 'h',
        'hour': 'h',
        'hours': 'h',
        'm': 'm',
        'minute': 'm',
        'minutes': 'm',
        's': 's',
        'second': 's',
        'seconds': 's',
    }
    SUFFIX_MULTIPLES = {
        'y': 60 * 60 * 24 * 365,
        'w': 60 * 60 * 24 * 7,
        'd': 60 * 60 * 24,
        'h': 60 * 60,
        'm': 60,
        's': 1,
    }
    total = 0
    pattern = re.compile(r'(\d+)[\s,]*([a-zA-Z]+)')
    for match in pattern.finditer(input_str):
        amount = int(match.group(1))
        suffix = match.group(2).lower()
        if suffix not in SUFFIX_MAP:
            raise ValueError(f'Intervalo inválido: {input_str}')
        index = SUFFIX_MAP[suffix]
        total += amount * SUFFIX_MULTIPLES[index]
    return total


def get_access_token():
    auth_url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': global_config['TWITCH_CLIENT_ID'],
        'client_secret': global_config['TWITCH_CLIENT_SECRET'],
        'grant_type': 'client_credentials'
    }
    response = requests.post(auth_url, params=params)
    return response.json().get('access_token')


def get_channel_id(channel_name):
    access_token = get_access_token()
    headers = {
        'Client-ID': global_config['TWITCH_CLIENT_ID'],
        'Authorization': f'Bearer {access_token}'
    }

    response = requests.get(
        f'https://api.twitch.tv/helix/users?login={channel_name}',
        headers=headers
    )

    if response.status_code == 200:
        data = response.json().get('data', [])
        return data[0]['id'] if data else None
    return None


def get_channel_videos(user_id):
    access_token = get_access_token()
    headers = {
        'Client-ID': global_config['TWITCH_CLIENT_ID'],
        'Authorization': f'Bearer {access_token}'
    }

    videos = []
    cursor = None

    while True:
        params = {'user_id': user_id, 'first': 100}
        if cursor:
            params['after'] = cursor

        response = requests.get(
            'https://api.twitch.tv/helix/videos',
            headers=headers,
            params=params
        )

        if response.status_code != 200:
            break

        data = response.json()
        videos.extend(data.get('data', []))

        cursor = data.get('pagination', {}).get('cursor')
        if not cursor:
            break

    return [v for v in videos if interval_string_to_seconds(v['duration']) <= int(global_config['MAX_VIDEO_TIME'])]


def get_channel_clips(user_id):
    access_token = get_access_token()
    headers = {
        'Client-ID': global_config['TWITCH_CLIENT_ID'],
        'Authorization': f'Bearer {access_token}'
    }

    clips = []
    cursor = None

    try:
        while len(clips) < 100:
            params = {
                'broadcaster_id': user_id,
                'first': 100,
                'started_at': '2020-01-01T00:00:00Z'
            }
            if cursor:
                params['after'] = cursor

            response = requests.get(
                'https://api.twitch.tv/helix/clips',
                headers=headers,
                params=params
            )

            if response.status_code != 200:
                break

            data = response.json()
            new_clips = [c for c in data.get('data', []) if c['duration'] <= int(global_config['MAX_VIDEO_TIME'])]
            clips.extend(new_clips)

            cursor = data.get('pagination', {}).get('cursor')
            if not cursor:
                break

        return clips[:100]

    except Exception as e:
        print(f"Erro nos clipes: {str(e)}")
        return []


def create_browser_source(video_url, video_duration):
    ws = obsws(global_config['OBS_HOST'], global_config['OBS_PORT'], global_config['OBS_PASSWORD'])
    try:
        ws.connect()

        scene_name = "Twitch Auto"
        source_name = "TwitchVideo"

        try:
            scene_item_id = ws.call(obsrequests.GetSceneItemId(
                sceneName=scene_name,
                sourceName=source_name
            )).datain.get('sceneItemId')

            if scene_item_id:
                ws.call(obsrequests.RemoveSceneItem(
                    sceneName=scene_name,
                    sceneItemId=scene_item_id
                ))
                time.sleep(0.5)
        except:
            pass

        settings = {
            "url": video_url + "&t=" + str(time.time()),
            "width": 1920,
            "height": 1080,
            "css": "body { margin: 0; overflow: hidden; }",
            "reroute_audio": False,
            "restart_when_active": True
        }

        creation_response = ws.call(obsrequests.CreateInput(
            sceneName=scene_name,
            inputName=source_name,
            inputKind="browser_source",
            inputSettings=settings,
            enabled=True
        ))

        if not creation_response.status:
            raise Exception("Falha ao criar fonte OBS")

        time.sleep(1)
        scene_item_id = ws.call(obsrequests.GetSceneItemId(
            sceneName=scene_name,
            sourceName=source_name
        )).datain.get('sceneItemId')

        if not scene_item_id:
            raise Exception("Fonte não encontrada")

        ws.call(obsrequests.SetSceneItemTransform(
            sceneName=scene_name,
            sceneItemId=scene_item_id,
            transform={
                "alignment": 5,
                "boundsAlignment": 5,
                "scaleX": 1.0,
                "scaleY": 1.0
            }
        ))

    except Exception as e:
        print(f"Erro OBS: {str(e)}")
        raise
    finally:
        ws.disconnect()


def remove_browser_source(time_to_sleep):
    print("remove_video sleep...")
    time.sleep(time_to_sleep + 1)
    print("remove_video!")
    ws = obsws(global_config['OBS_HOST'], global_config['OBS_PORT'], global_config['OBS_PASSWORD'])
    try:
        ws.connect()

        scene_name = "Twitch Auto"
        source_name = "TwitchVideo"
        scene_item_id = ws.call(obsrequests.GetSceneItemId(
            sceneName=scene_name,
            sourceName=source_name
        )).datain.get('sceneItemId')

        if scene_item_id:
            ws.call(obsrequests.RemoveSceneItem(
                sceneName=scene_name,
                sceneItemId=scene_item_id
            ))
    except Exception as e:
        print(f"Erro ao remover cena: {str(e)}")
        ws.disconnect()
        raise
    finally:
        ws.disconnect()


@app.route('/play', methods=['POST'])
def play_random_video():
    global selected_video_duration
    try:
        data = request.json
        channel = data.get('channel')
        if not channel:
            return jsonify({'error': 'Nome do canal necessário'}), 400

        print(f"\nIniciando requisição para: {channel}")

        user_id = get_channel_id(channel)
        if not user_id:
            return jsonify({'error': 'Canal não encontrado'}), 404

        media_type = "clipe"
        content = get_channel_clips(user_id)
        if not content:
            media_type = "vídeo"
            content = get_channel_videos(user_id)
            if not content:
                return jsonify({'error': 'Nenhum conteúdo encontrado'}), 404

        selected = random.choice(content)
        selected_video_duration = selected['duration'] if media_type == "clipe" else interval_string_to_seconds(
            selected['duration'])

        if media_type == "clipe":
            embed_url = f"https://clips.twitch.tv/embed?clip={selected['id']}&parent=twitch.tv&autoplay=true"
        else:
            video_id = selected['url'].split('/')[-1]
            embed_url = f"https://player.twitch.tv/?video=v{video_id}&parent=twitch.tv&autoplay=true"

        print(f"Reproduzindo {media_type}: {selected['title']}")
        create_browser_source(embed_url, selected_video_duration)

        return jsonify({
            'status': 'success',
            'channel': channel,
            'media_type': media_type,
            'title': selected['title'],
            'duration': selected_video_duration
        }), 200

    except Exception as e:
        print(f"Erro completo: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500
    # finally:
    # remove_video(duration)


def load_or_create_config():
    default_config = {
        'TWITCH_CLIENT_ID': 'your_client_id',
        'TWITCH_CLIENT_SECRET': 'your_client_secret',
        'OBS_HOST': 'localhost',
        'OBS_PORT': 4455,
        'OBS_PASSWORD': 'obs_websocket_password',
        'TWITCH_USERNAME': 'your_username',
        'AUTHORIZED_USERS': ['some_username'],
        'TWITCH_REDIRECT_URI': 'http://localhost:5000/auth/callback',
        'MAX_VIDEO_TIME': 30
    }

    try:
        with open("config.yaml", "r") as file:
            config = yaml.safe_load(file)
            if 'AUTHORIZED_USERS' not in config:
                config['AUTHORIZED_USERS'] = default_config['AUTHORIZED_USERS']
            elif not isinstance(config['AUTHORIZED_USERS'], list):
                config['AUTHORIZED_USERS'] = [config['AUTHORIZED_USERS']]
    except FileNotFoundError:
        config = default_config
        with open("config.yaml", "w") as file:
            yaml.dump(config, file)

    return config


@app.route('/config', methods=['GET', 'POST'])
def config_editor():
    global global_config
    message = None
    message_type = 'success'

    if request.method == 'POST':
        try:

            auth_users = []
            for user in request.form['AUTHORIZED_USERS'].split(','):
                user = user.strip()
                if user and re.match(r'^[a-zA-Z0-9_]{4,25}$', user):
                    auth_users.append(user)

            if not auth_users:
                raise ValueError("Pelo menos um usuário autorizado deve ser informado")

            new_config = {
                'TWITCH_CLIENT_ID': request.form['TWITCH_CLIENT_ID'],
                'TWITCH_CLIENT_SECRET': request.form['TWITCH_CLIENT_SECRET'],
                'OBS_HOST': request.form['OBS_HOST'],
                'OBS_PORT': int(request.form['OBS_PORT']),
                'OBS_PASSWORD': request.form['OBS_PASSWORD'],
                'TWITCH_USERNAME': request.form['TWITCH_USERNAME'],
                'TWITCH_REDIRECT_URI': global_config['TWITCH_REDIRECT_URI'],
                'AUTHORIZED_USERS': auth_users,
                'MAX_VIDEO_TIME': request.form['MAX_VIDEO_TIME']
            }

            global_config = new_config
            save_config()

            # Dispara o reinício do bot
            restart_bot_event.set()

            message = "Configurações salvas e aplicação reiniciada!"
        except Exception as e:
            message = f"Erro: {str(e)}"
            message_type = 'error'

    return render_template_string(CONFIG_TEMPLATE, config=global_config,
                                  message=message, message_type=message_type)


def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)


def run_bot():
    while True:
        try:
            if restart_bot_event.is_set():
                restart_bot_event.clear()
                print("Reiniciando bot com novas configurações...")

            tokens = load_tokens()
            if not tokens or tokens['expires_at'] <= time.time():
                if not refresh_tokens():
                    print("Requer autenticação...")
                    start_auth_flow()
                    auth_complete_event.wait()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            bot = TwitchBot()
            loop.run_until_complete(bot.start())

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Erro: {str(e)}")
            time.sleep(5)
        finally:
            if loop.is_running():
                loop.close()


if __name__ == '__main__':
    load_config()

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    time.sleep(2)

    if global_config.get('TWITCH_CLIENT_ID') == 'your_client_id':
        print("\nAcesse http://localhost:5000/config para configurar\n")

    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()

    try:
        while True:
            time.sleep(1)
            if app_should_restart.is_set():
                print("Reiniciando aplicação completa...")
                # Lógica para reiniciar todos os componentes
                restart_bot_event.set()
                app_should_restart.clear()
    except KeyboardInterrupt:
        flask_thread.join()
        bot_thread.join()
