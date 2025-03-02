import traceback
import requests
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
import time
from obswebsocket import obsws, requests as obsrequests
import re
import yaml
import asyncio
from twitchio.ext import commands
import threading

app = Flask(__name__)
CORS(app)

with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

# Configurações
TWITCH_CLIENT_ID = config.get("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = config.get("TWITCH_CLIENT_SECRET")
TWITCH_OAUTH_TOKEN = config.get("TWITCH_OAUTH_TOKEN")
TWITCH_USERNAME = config.get("TWITCH_USERNAME")

# Configurações OBS
OBS_HOST = config.get("OBS_HOST")
OBS_PORT = config.get("OBS_PORT")
OBS_PASSWORD = config.get("OBS_PASSWORD")

global selected_video_duration

class TwitchBot(commands.Bot):
    def __init__(self):
        super().__init__(
            token=TWITCH_OAUTH_TOKEN,
            client_id=TWITCH_CLIENT_ID,
            nick=TWITCH_USERNAME,
            prefix='!',
            initial_channels=[TWITCH_USERNAME.lower()]
        )

    async def event_ready(self):
        print(f'Bot conectado como {self.nick}')
        # print(f'Conectado no canal: {self.initial_channels}')

    async def event_message(self, message):
        if message.echo:
            return
        await self.handle_commands(message)

    @commands.command(name='so')
    async def shoutout_command(self, ctx, channel_name: str = None):
        # Verificar se é moderador ou broadcaster
        if not (ctx.author.is_mod or ctx.author.name.lower() == TWITCH_USERNAME.lower()):
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
        'client_id': TWITCH_CLIENT_ID,
        'client_secret': TWITCH_CLIENT_SECRET,
        'grant_type': 'client_credentials'
    }
    response = requests.post(auth_url, params=params)
    return response.json().get('access_token')


def get_channel_id(channel_name):
    access_token = get_access_token()
    headers = {
        'Client-ID': TWITCH_CLIENT_ID,
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
        'Client-ID': TWITCH_CLIENT_ID,
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

    return [v for v in videos if interval_string_to_seconds(v['duration']) <= 30]


def get_channel_clips(user_id):
    access_token = get_access_token()
    headers = {
        'Client-ID': TWITCH_CLIENT_ID,
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
            new_clips = [c for c in data.get('data', []) if c['duration'] <= 30]
            clips.extend(new_clips)

            cursor = data.get('pagination', {}).get('cursor')
            if not cursor:
                break

        return clips[:100]

    except Exception as e:
        print(f"Erro nos clipes: {str(e)}")
        return []


def create_browser_source(video_url, video_duration):
    ws = obsws(OBS_HOST, OBS_PORT, OBS_PASSWORD)
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
    time.sleep(time_to_sleep+1)
    print("remove_video!")
    ws = obsws(OBS_HOST, OBS_PORT, OBS_PASSWORD)
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
        selected_video_duration = selected['duration'] if media_type == "clipe" else interval_string_to_seconds(selected['duration'])

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
    #finally:
        #remove_video(duration)


def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)


def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    bot = TwitchBot()

    try:
        loop.run_until_complete(bot.start())
    except KeyboardInterrupt:
        loop.run_until_complete(bot.close())
    finally:
        loop.close()


if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    bot_thread = threading.Thread(target=run_bot)

    flask_thread.start()
    time.sleep(2)
    bot_thread.start()

    flask_thread.join()
    bot_thread.join()
