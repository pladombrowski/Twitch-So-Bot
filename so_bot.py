"""
Improved version of the Twitch SO Bot with better code organization,
performance optimizations, and error handling.
"""
import traceback
import requests
import random
import time
import re
import yaml
import asyncio
import threading
import webbrowser
import csv
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
import urllib3
import aiohttp

# Disable warnings for insecure requests (necessary for self-signed certificates)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from obswebsocket import obsws, requests as obs_requests
from twitchio.ext import commands


class Config:
    """Class to manage application configuration"""

    DEFAULT_CONFIG = {
        'TWITCH_CLIENT_ID': 'your_client_id',
        'TWITCH_CLIENT_SECRET': 'your_client_secret',
        'OBS_HOST': 'localhost',
        'OBS_PORT': 4455,
        'OBS_PASSWORD': 'obs_websocket_password',
        'TWITCH_USERNAME': 'your_username',
        'TWITCH_REDIRECT_URI': 'https://localhost:5000/auth/callback',
        'BLOCKED_PERIOD': '08-23',
        'AUTHORIZED_USERS': [],
        'CONTENT_TYPES': ['clip', 'video', 'highlight'],
        'LOG_FILE_PATH': 'command_log.csv',
        'MAX_VIDEO_TIME': '30'
    }

    def __init__(self, config_path: str = "config.yaml"):
        """Initialize configuration from file or defaults"""
        self.config_path = config_path
        self.config = self.load()

    def load(self) -> Dict[str, Any]:
        """Load configuration from file or use defaults"""
        try:
            with open(self.config_path, "r") as file:
                config = yaml.safe_load(file)
                # Set default if not exists
                if 'BLOCKED_PERIOD' not in config:
                    config['BLOCKED_PERIOD'] = '08-23'
                return config
        except FileNotFoundError:
            # If file not found, create it with default config and return default config
            self.save_default()
            return self.DEFAULT_CONFIG.copy()

    def save_default(self) -> None:
        """Save default configuration to file"""
        with open(self.config_path, "w") as file:
            yaml.dump(self.DEFAULT_CONFIG, file)

    def save(self) -> None:
        """Save current configuration to file"""
        with open(self.config_path, "w") as file:
            yaml.dump(self.config, file)

    def save(self) -> None:
        """Save configuration to file"""
        with open(self.config_path, "w") as file:
            yaml.dump(self.config, file)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with optional default"""
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value"""
        self.config[key] = value

    def update(self, new_config: Dict[str, Any]) -> None:
        """Update configuration with new values"""
        self.config.update(new_config)
        self.save()


class TokenManager:
    """Class to manage Twitch API tokens"""

    def __init__(self, config: Config, tokens_path: str = "tokens.yaml"):
        """Initialize token manager"""
        self.config = config
        self.tokens_path = tokens_path
        self.auth_complete_event = threading.Event()

    def load_tokens(self) -> Optional[Dict[str, Any]]:
        """Load tokens from file"""
        try:
            with open(self.tokens_path, "r") as f:
                tokens = yaml.safe_load(f)
                if tokens and 'access_token' in tokens and 'refresh_token' in tokens:
                    return tokens
        except FileNotFoundError:
            pass
        return None

    def save_tokens(self, access_token: str, refresh_token: str, expires_in: int) -> None:
        """Save tokens to file"""
        tokens = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': time.time() + expires_in
        }
        with open(self.tokens_path, "w") as f:
            yaml.dump(tokens, f)

    async def refresh_tokens(self) -> bool:
        """Refresh tokens using the refresh token"""
        tokens = self.load_tokens()
        if not tokens or 'refresh_token' not in tokens:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://id.twitch.tv/oauth2/token',
                    data={  # Changed from params to data
                        'client_id': self.config.get('TWITCH_CLIENT_ID'),
                        'client_secret': self.config.get('TWITCH_CLIENT_SECRET'),
                        'grant_type': 'refresh_token',
                        'refresh_token': tokens['refresh_token']
                    }
                ) as response:
                    response.raise_for_status()
                    token_data = await response.json()
                    self.save_tokens(
                        token_data['access_token'],
                        token_data.get('refresh_token', tokens['refresh_token']),
                        token_data['expires_in']
                    )
                    return True
        except Exception as e:
            print(f"Error refreshing token: {str(e)}")
            return False

    async def get_valid_token(self) -> Optional[str]:
        """Get a valid access token, refreshing if necessary"""
        tokens = self.load_tokens()

        if tokens and tokens['expires_at'] > time.time() + 60:  # 1 minute margin
            return tokens['access_token']

        if tokens and await self.refresh_tokens(): # Made call async
            return self.load_tokens()['access_token']

        return None

    async def get_app_access_token(self) -> Optional[str]:
        """Get an application access token for API requests"""
        auth_url = 'https://id.twitch.tv/oauth2/token'
        params = {
            'client_id': self.config.get('TWITCH_CLIENT_ID'),
            'client_secret': self.config.get('TWITCH_CLIENT_SECRET'),
            'grant_type': 'client_credentials'
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(auth_url, data=params) as response: # Changed from params to data
                    response.raise_for_status()
                    token_data = await response.json()
                    return token_data.get('access_token')
        except Exception as e:
            print(f"Error getting app access token: {str(e)}")
            return None

    def start_auth_flow(self) -> None:
        """Start the OAuth authentication flow"""
        # Use hardcoded redirect URI that supports both HTTP and HTTPS
        redirect_uri = "https://localhost:5000/auth/callback" # Changed to HTTPS
        params = {
            'client_id': self.config.get('TWITCH_CLIENT_ID'),
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'chat:read chat:edit'
        }
        auth_url = requests.Request('GET', 'https://id.twitch.tv/oauth2/authorize', params=params).prepare().url
        print(f"Please authorize the application: {auth_url}")
        webbrowser.open(auth_url)


class CommandLogger:
    """Class to log command usage"""

    def __init__(self, config: Config):
        """Initialize command logger"""
        self.config = config

    def log_command(self, command: str, channel: str, requester: str) -> None:
        """Log command usage to CSV file"""
        log_file = self.config.get('LOG_FILE_PATH', 'command_log.csv')
        fieldnames = ['timestamp', 'command', 'channel', 'requester']

        new_entry = {
            'timestamp': datetime.now().isoformat(),
            'command': command,
            'channel': channel.lower(),
            'requester': requester.lower(),
        }

        try:
            with open(log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if f.tell() == 0:
                    writer.writeheader()
                writer.writerow(new_entry)
        except Exception as e:
            print(f"Error logging command: {str(e)}")


class TimeBlocker:
    """Class to handle time-based command blocking"""

    def __init__(self, config: Config):
        """Initialize time blocker"""
        self.config = config

    def is_command_blocked(self) -> bool:
        """Check if commands are currently blocked based on time"""
        try:
            blocked_period = self.config.get('BLOCKED_PERIOD', '08-22')
            start_hour, end_hour = map(int, blocked_period.split('-'))
            current_hour = datetime.now().hour

            if start_hour < end_hour:
                return start_hour <= current_hour < end_hour
            else:
                return current_hour >= start_hour or current_hour < end_hour
        except Exception:
            return False


class TwitchAPI:
    """Class to interact with Twitch API"""

    def __init__(self, config: Config, token_manager: TokenManager):
        """Initialize Twitch API client"""
        self.config = config
        self.token_manager = token_manager
        self._channel_cache = {}  # Cache for channel IDs
        self._content_cache = {}  # Cache for channel content
        self._cache_expiry = {}   # Expiry times for cache entries
        self.cache_duration = 300  # Cache duration in seconds (5 minutes)

    async def get_channel_id(self, channel_name: str) -> Optional[str]:
        """Get channel ID from channel name, using cache if available"""
        current_time = time.time()
        if channel_name in self._channel_cache and self._cache_expiry.get(f"channel_{channel_name}", 0) > current_time:
            return self._channel_cache[channel_name]

        access_token = await self.token_manager.get_app_access_token()
        if not access_token:
            print("Error: Could not retrieve app access token for get_channel_id.")
            return None
        headers = {
            'Client-ID': self.config.get('TWITCH_CLIENT_ID'),
            'Authorization': f'Bearer {access_token}'
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'https://api.twitch.tv/helix/users?login={channel_name}',
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        data_list = data.get('data', [])
                        if data_list:
                            channel_id = data_list[0]['id']
                            self._channel_cache[channel_name] = channel_id
                            self._cache_expiry[f"channel_{channel_name}"] = current_time + self.cache_duration
                            return channel_id
                    else:
                        print(f"Error getting channel ID: {response.status} - {await response.text()}")
            return None
        except Exception as e:
            print(f"Error getting channel ID: {str(e)}")
            return None

    async def get_channel_clips(self, user_id: str) -> List[Dict[str, Any]]:
        """Get clips for a channel"""
        access_token = await self.token_manager.get_app_access_token()
        if not access_token:
            print("Error: Could not retrieve app access token for get_channel_clips.")
            return []
        headers = {
            'Client-ID': self.config.get('TWITCH_CLIENT_ID'),
            'Authorization': f'Bearer {access_token}'
        }

        clips = []
        cursor = None
        max_video_time = int(self.config.get('MAX_VIDEO_TIME'))

        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    params = {
                        'broadcaster_id': user_id,
                        'first': 100,
                    }
                    if cursor:
                        params['after'] = cursor

                    async with session.get(
                        'https://api.twitch.tv/helix/clips',
                        headers=headers,
                        params=params
                    ) as response:
                        if response.status != 200:
                            print(f"Error getting clips: {response.status} - {await response.text()}")
                            break
                        data = await response.json()
                        new_clips = [c for c in data.get('data', []) if c['duration'] <= max_video_time]
                        clips.extend(new_clips)
                        cursor = data.get('pagination', {}).get('cursor')
                        if not cursor or len(clips) >= 100: # Avoid excessive pagination if already have 100 clips within time limit
                            break
            return clips
        except Exception as e:
            print(f"Error getting clips: {str(e)}")
            return []

    async def get_channel_videos(self, user_id: str, video_type: str) -> List[Dict[str, Any]]:
        """Get videos for a channel"""
        access_token = await self.token_manager.get_app_access_token()
        if not access_token:
            print("Error: Could not retrieve app access token for get_channel_videos.")
            return []
        headers = {
            'Client-ID': self.config.get('TWITCH_CLIENT_ID'),
            'Authorization': f'Bearer {access_token}'
        }

        videos = []
        cursor = None
        max_video_time = int(self.config.get('MAX_VIDEO_TIME'))

        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    params = {
                        'user_id': user_id,
                        'first': 100, # Max allowed by Twitch API is 100
                        'type': video_type
                    }
                    if cursor:
                        params['after'] = cursor

                    async with session.get(
                        'https://api.twitch.tv/helix/videos',
                        headers=headers,
                        params=params
                    ) as response:
                        if response.status != 200:
                            print(f"Error getting videos: {response.status} - {await response.text()}")
                            break
                        data = await response.json()
                        videos.extend(data.get('data', []))
                        cursor = data.get('pagination', {}).get('cursor')
                        if not cursor: # No more pages
                            break
            
            filtered = []
            for v in videos:
                try:
                    duration = self._interval_string_to_seconds(v['duration'])
                    if duration <= max_video_time:
                        filtered.append(v)
                except Exception as e:
                    print(f"Error processing video duration: {str(e)} for video {v.get('id')}")
                    continue
            return filtered
        except Exception as e:
            print(f"Error getting videos: {str(e)}")
            return []

    async def get_channel_content(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all content (clips, videos, highlights) for a channel"""
        current_time = time.time()
        if user_id in self._content_cache and self._cache_expiry.get(f"content_{user_id}", 0) > current_time:
            return self._content_cache[user_id]

        content = []
        content_types = self.config.get('CONTENT_TYPES', [])
        max_video_time = int(self.config.get('MAX_VIDEO_TIME'))

        # Get clips
        if 'clip' in content_types:
            clips_data = await self.get_channel_clips(user_id)
            for clip in clips_data:
                clip.update({
                    'content_type': 'clip',
                    'embed_url': f"https://clips.twitch.tv/embed?clip={clip['id']}&parent=twitch.tv&autoplay=true",
                    'duration_seconds': clip['duration'] 
                })
            content.extend(clips_data)

        # Get videos
        if 'video' in content_types:
            videos_data = await self.get_channel_videos(user_id, 'archive')
            for video in videos_data:
                video_id = video['url'].split('/')[-1]
                video.update({
                    'content_type': 'video',
                    'embed_url': f"https://player.twitch.tv/?video=v{video_id}&parent=twitch.tv&autoplay=true",
                    'duration_seconds': self._interval_string_to_seconds(video['duration'])
                })
            content.extend(videos_data)

        # Get highlights
        if 'highlight' in content_types:
            highlights_data = await self.get_channel_videos(user_id, 'highlight')
            for highlight in highlights_data:
                video_id = highlight['url'].split('/')[-1]
                highlight.update({
                    'content_type': 'highlight',
                    'embed_url': f"https://player.twitch.tv/?video=v{video_id}&parent=twitch.tv&autoplay=true",
                    'duration_seconds': self._interval_string_to_seconds(highlight['duration'])
                })
            content.extend(highlights_data)
        
        # Filter by duration and update cache
        # Ensure duration_seconds is present and is a number before filtering
        filtered_content = [c for c in content if isinstance(c.get('duration_seconds'), (int, float)) and c['duration_seconds'] <= max_video_time]

        self._content_cache[user_id] = filtered_content
        self._cache_expiry[f"content_{user_id}"] = current_time + self.cache_duration

        return filtered_content

    @staticmethod
    def _interval_string_to_seconds(input_str: str) -> int:
        """Convert Twitch duration string to seconds"""
        suffix_map = {
            'y': 'y', 'year': 'y', 'years': 'y',
            'w': 'w', 'week': 'w', 'weeks': 'w',
            'd': 'd', 'day': 'd', 'days': 'd',
            'h': 'h', 'hour': 'h', 'hours': 'h',
            'm': 'm', 'minute': 'm', 'minutes': 'm',
            's': 's', 'second': 's', 'seconds': 's',
        }
        suffix_multiples = {
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
            if suffix not in suffix_map:
                raise ValueError(f'Invalid interval: {input_str}')
            index = suffix_map[suffix]
            total += amount * suffix_multiples[index]
        return total


class OBSController:
    """Class to control OBS via WebSocket"""

    def __init__(self, config: Config):
        """Initialize OBS controller"""
        self.config = config
        self.scene_name = "Twitch Auto"
        self.source_name = "TwitchVideo"

    def create_browser_source(self, video_url: str) -> None:
        """Create or update browser source in OBS"""
        ws = obsws(
            self.config.get('OBS_HOST'), 
            self.config.get('OBS_PORT'), 
            self.config.get('OBS_PASSWORD')
        )
        try:
            ws.connect()

            # Try to remove existing source if it exists
            try:
                scene_item_id = ws.call(obs_requests.GetSceneItemId(
                    sceneName=self.scene_name,
                    sourceName=self.source_name
                )).datain.get('sceneItemId')

                if scene_item_id:
                    ws.call(obs_requests.RemoveSceneItem(
                        sceneName=self.scene_name,
                        sceneItemId=scene_item_id
                    ))
                    time.sleep(0.5)
            except Exception:
                pass  # Ignore if source doesn't exist

            # Create new browser source
            settings = {
                "url": video_url + "&t=" + str(time.time()),
                "width": 1920,
                "height": 1080,
                "css": "body { margin: 0; overflow: hidden; }",
                "reroute_audio": False,
                "restart_when_active": True
            }

            creation_response = ws.call(obs_requests.CreateInput(
                sceneName=self.scene_name,
                inputName=self.source_name,
                inputKind="browser_source",
                inputSettings=settings,
                enabled=True
            ))

            if not creation_response.status:
                raise Exception("Failed to create OBS source")

            # Set transform properties
            time.sleep(1)
            scene_item_id = ws.call(obs_requests.GetSceneItemId(
                sceneName=self.scene_name,
                sourceName=self.source_name
            )).datain.get('sceneItemId')

            if not scene_item_id:
                raise Exception("Source not found")

            ws.call(obs_requests.SetSceneItemTransform(
                sceneName=self.scene_name,
                sceneItemId=scene_item_id,
                transform={
                    "alignment": 5,
                    "boundsAlignment": 5,
                    "scaleX": 1.0,
                    "scaleY": 1.0
                }
            ))

        except Exception as e:
            print(f"OBS Error: {str(e)}")
            raise
        finally:
            ws.disconnect()

    def remove_browser_source(self, time_to_sleep: int) -> None:
        """Remove browser source after specified time"""
        def delayed_remove():
            print(f"Removing video in {time_to_sleep} seconds...")
            time.sleep(time_to_sleep + 1)
            print("Removing video!")

            ws = obsws(
                self.config.get('OBS_HOST'), 
                self.config.get('OBS_PORT'), 
                self.config.get('OBS_PASSWORD')
            )
            try:
                ws.connect()

                scene_item_id = ws.call(obs_requests.GetSceneItemId(
                    sceneName=self.scene_name,
                    sourceName=self.source_name
                )).datain.get('sceneItemId')

                if scene_item_id:
                    ws.call(obs_requests.RemoveSceneItem(
                        sceneName=self.scene_name,
                        sceneItemId=scene_item_id
                    ))
            except Exception as e:
                print(f"Error removing scene: {str(e)}")
            finally:
                ws.disconnect()

        # Start removal in a separate thread to not block
        threading.Thread(target=delayed_remove, daemon=True).start()


class TwitchBot(commands.Bot):
    """Twitch bot for handling chat commands"""

    def __init__(self, token: str, config: Config, token_manager: TokenManager, 
                 time_blocker: TimeBlocker, command_logger: CommandLogger):
        """Initialize Twitch bot"""
        self.config = config
        self.token_manager = token_manager
        self.time_blocker = time_blocker
        self.command_logger = command_logger
        self.restart_event = threading.Event()

        # Token is now passed as an argument
        super().__init__(
            token=token,
            client_id=self.config.get('TWITCH_CLIENT_ID'),
            nick=self.config.get('TWITCH_USERNAME'),
            prefix='!',
            initial_channels=[self.config.get('TWITCH_USERNAME').lower()]
        )

    async def monitor_restart(self):
        """Monitor for restart signal"""
        while not self.restart_event.is_set():
            await asyncio.sleep(1)
        await self.close()

    async def start(self):
        """Start the bot with restart monitoring"""
        self.loop.create_task(self.monitor_restart())
        await super().start()

    async def event_ready(self):
        """Called when the bot is ready"""
        print(f'Bot connected as {self.nick}')

    async def event_error(self, error, data=None):
        """Handle errors"""
        if 'Authentication failed' in str(error):
            print("Invalid token, trying to refresh...")
            # Ensure refresh_tokens is awaited
            refreshed = await self.token_manager.refresh_tokens()
            if refreshed:
                # Ensure get_valid_token is awaited
                self.token = await self.token_manager.get_valid_token()
                await self.close()
                self._connection._token = self.token
                await self.connect()
            else:
                print("Token refresh failed. Authentication required.")
                self.token_manager.auth_complete_event.clear()
                self.token_manager.start_auth_flow()

    async def event_message(self, message):
        """Handle incoming messages"""
        if message.echo:
            return
        await self.handle_commands(message)

    def is_user_authorized(self, ctx):
        """Check if user is authorized to use commands"""
        authorized_users = [user.lower() for user in self.config.get('AUTHORIZED_USERS', [])]
        return (
            ctx.author.name.lower() in authorized_users or
            ctx.author.is_mod or
            ctx.author.name.lower() == self.config.get('TWITCH_USERNAME').lower()
        )


    @commands.command(name='so')
    async def shoutout_command(self, ctx, *args):
        """Handle the !so command and its subcommands"""
        if not self.is_user_authorized(ctx):
            await ctx.send("❌ Você não tem permissão para usar este comando!")
            return

        # Check for subcommands
        if args and args[0].lower() == "clean_queue":
            await self.clean_queue_subcommand(ctx)
            return

        # Regular !so command with channel name
        channel_name = args[0] if args else None

        if self.time_blocker.is_command_blocked():
            await ctx.send("⏰ O !so está bloqueado neste horário!")
            return

        if not channel_name:
            await ctx.send("Formato correto: !so <nome_do_canal> ou !so clean_queue")
            return

        if not re.match(r'^[a-zA-Z0-9_]{4,25}$', channel_name):
            await ctx.send("Nome de canal inválido")
            return

        try:
            # Create a connector that skips SSL verification
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(
                    'https://localhost:5000/play',
                    json={'channel': channel_name},
                    timeout=35
                ) as response:
                    if response.status == 200:
                        self.command_logger.log_command(
                            command='so',
                            channel=channel_name.lower(),
                            requester=ctx.author.name
                        )
                        response_data = await response.json()
                        queue_position = response_data.get('queue_position', 1)

                        if queue_position > 1:
                            await ctx.send(f"🎥 Conteúdo de {channel_name} adicionado à fila! Posição: {queue_position}")
                        else:
                            await ctx.send(f"🎥 Reproduzindo conteúdo de {channel_name}!")
                    else:
                        error_msg = (await response.json()).get('error', 'Erro desconhecido')
                        await ctx.send(f"❌ Erro: {error_msg}")

        except Exception as e:
            print(f"Error in request: {str(e)}")
            await ctx.send("🔧 Erro interno ao processar o pedido")

    async def clean_queue_subcommand(self, ctx):
        """Handle the !so clean_queue subcommand"""
        try:
            # Create a connector that skips SSL verification
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(
                    'https://localhost:5000/clean_queue',
                    timeout=10
                ) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        message = response_data.get('message', 'Fila limpa com sucesso!')
                        await ctx.send(f"🧹 {message}")
                    else:
                        error_msg = (await response.json()).get('error', 'Erro desconhecido')
                        await ctx.send(f"❌ Erro ao limpar a fila: {error_msg}")

        except Exception as e:
            print(f"Error in clean_queue request: {str(e)}")
            await ctx.send("🔧 Erro interno ao limpar a fila")


class FlaskApp:
    """Flask web application for configuration and API endpoints"""

    def __init__(self, config: Config, token_manager: TokenManager, 
                 twitch_api: TwitchAPI, obs_controller: OBSController):
        """Initialize Flask app"""
        self.app = Flask(__name__)
        CORS(self.app)
        self.config = config
        self.token_manager = token_manager
        self.twitch_api = twitch_api
        self.obs_controller = obs_controller
        self.selected_video_duration = 0

        # Command queue system
        self.command_queue = []
        self.is_playing = False
        self.queue_lock = threading.Lock()
        self.queue_processor_thread = None

        # Register routes
        self.register_routes()

    def register_routes(self):
        """Register Flask routes"""

        @self.app.route('/auth/callback')
        def auth_callback():
            """Handle OAuth callback"""
            code = request.args.get('code')
            if not code:
                return jsonify({'error': 'Authorization code missing'}), 400

            try:
                response = requests.post(
                    'https://id.twitch.tv/oauth2/token',
                    data={  # Changed from params to data
                        'client_id': self.config.get('TWITCH_CLIENT_ID'),
                        'client_secret': self.config.get('TWITCH_CLIENT_SECRET'),
                        'code': code,
                        'grant_type': 'authorization_code',
                        'redirect_uri': "https://localhost:5000/auth/callback"
                    }
                )
                response.raise_for_status()

                token_data = response.json()
                self.token_manager.save_tokens(
                    token_data['access_token'],
                    token_data['refresh_token'],
                    token_data['expires_in']
                )
                self.token_manager.auth_complete_event.set()
                return render_template("auth-callback.html")
            except Exception as e:
                print(f"Authentication error: {str(e)}")
                # You might want to render an error page here as well
                return jsonify({'error': 'Authentication failed', 'details': str(e)}), 500


        @self.app.route('/play', methods=['POST'])
        def play_random_video():
            """API endpoint to play a random video"""
            try:
                data = request.json
                channel = data.get('channel')
                if not channel:
                    return jsonify({'error': 'Channel name required'}), 400

                # Add the channel to the queue
                with self.queue_lock:
                    self.command_queue.append(channel)

                    # Start the queue processor if it's not already running
                    if not self.is_playing:
                        self.queue_processor_thread = threading.Thread(
                            target=self.process_queue,
                            daemon=True
                        )
                        self.queue_processor_thread.start()

                return jsonify({
                    'status': 'success',
                    'message': f'Added {channel} to the queue',
                    'queue_position': len(self.command_queue)
                }), 200

            except Exception as e:
                print(f"Complete error: {traceback.format_exc()}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/clean_queue', methods=['POST'])
        def clean_queue():
            """API endpoint to clean the command queue"""
            try:
                with self.queue_lock:
                    queue_size = len(self.command_queue)
                    self.command_queue.clear()

                return jsonify({
                    'status': 'success',
                    'message': f'Queue cleared ({queue_size} items removed)'
                }), 200

            except Exception as e:
                print(f"Error cleaning queue: {str(e)}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/config', methods=['GET', 'POST'])
        def config_editor():
            """Configuration web interface"""
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
                        raise ValueError("At least one authorized user must be specified")

                    # Validate blocked period
                    block_start = request.form['BLOCK_START'].zfill(2)
                    block_end = request.form['BLOCK_END'].zfill(2)

                    if not (0 <= int(block_start) <= 23 and 0 <= int(block_end) <= 23):
                        raise ValueError("Hours must be between 00 and 23")

                    new_config = {
                        'TWITCH_CLIENT_ID': request.form['TWITCH_CLIENT_ID'],
                        'TWITCH_CLIENT_SECRET': request.form['TWITCH_CLIENT_SECRET'],
                        'OBS_HOST': request.form['OBS_HOST'],
                        'OBS_PORT': int(request.form['OBS_PORT']),
                        'OBS_PASSWORD': request.form['OBS_PASSWORD'],
                        'TWITCH_USERNAME': request.form['TWITCH_USERNAME'],
                        'AUTHORIZED_USERS': auth_users,
                        'CONTENT_TYPES': request.form.getlist('CONTENT_TYPES'),
                        'LOG_FILE_PATH': request.form['LOG_FILE_PATH'],
                        'BLOCKED_PERIOD': f"{block_start}-{block_end}",
                        'MAX_VIDEO_TIME': request.form['MAX_VIDEO_TIME']
                    }

                    self.config.update(new_config)


                    # Signal application to proceed (starts the bot if it wasn't running)
                    app_instance.app_should_restart.set()

                    message = "Settings saved and application will start!"
                except Exception as e:
                    message_type = 'error'

            return render_template("config.html", 
                                         config=self.config.config,
                                         message=message, 
                                         message_type=message_type)

    def process_queue(self):
        """Process the command queue"""
        while True:
            with self.queue_lock:
                if not self.command_queue:
                    self.is_playing = False
                    return

                self.is_playing = True
                channel = self.command_queue.pop(0)
            
            # Create a new event loop for this thread if one doesn't exist
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            try:
                user_id = asyncio.run(self.twitch_api.get_channel_id(channel))
                if not user_id:
                    print(f"Channel not found: {channel}")
                    continue

                content_list = asyncio.run(self.twitch_api.get_channel_content(user_id))
                if not content_list:
                    print(f"No content found for channel: {channel}")
                    continue

                selected = random.choice(content_list)
                self.selected_video_duration = selected['duration_seconds']

                # Play the video
                self.obs_controller.create_browser_source(selected['embed_url'])

                # Schedule removal after video duration
                self.obs_controller.remove_browser_source(self.selected_video_duration)

                # Wait for the video to finish before processing next item
                time.sleep(self.selected_video_duration + 2)

            except Exception as e:
                print(f"Error processing queue item: {str(e)}")
                traceback.print_exc()

    def run(self, host='0.0.0.0', port=5000):
        """Run the Flask app"""
        # Enable SSL with 'adhoc' to use a self-signed certificate
        self.app.run(host=host, port=port, debug=True, use_reloader=False, ssl_context='adhoc')


class Application:
    """Main application class"""

    def __init__(self):
        """Initialize application components"""
        self.config = Config()
        self.token_manager = TokenManager(self.config)
        self.time_blocker = TimeBlocker(self.config)
        self.command_logger = CommandLogger(self.config)
        self.twitch_api = TwitchAPI(self.config, self.token_manager)
        self.obs_controller = OBSController(self.config)
        self.flask_app = FlaskApp(self.config, self.token_manager, self.twitch_api, self.obs_controller)

        self.restart_bot_event = threading.Event()
        self.app_should_restart = threading.Event()

    def run_flask(self):
        """Run the Flask web server"""
        self.flask_app.run()

    def run_bot(self):
        """Run the Twitch bot"""
        while True:
            try:
                if self.restart_bot_event.is_set():
                    self.restart_bot_event.clear()
                    print("Restarting bot with new configuration...")

                # Setup event loop for async operations if not already running
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed(): # Check if the loop was closed previously
                        raise RuntimeError
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # Perform async token checks and refresh if necessary
                valid_token = loop.run_until_complete(self.token_manager.get_valid_token())
                if not valid_token:
                    print("Authentication required or token refresh failed...")
                    # Start auth flow (synchronous) and wait for completion
                    self.token_manager.start_auth_flow()
                    self.token_manager.auth_complete_event.wait() # This blocks the bot thread until auth is done
                    # After auth, try to get the token again
                    valid_token = loop.run_until_complete(self.token_manager.get_valid_token())
                    if not valid_token:
                        print("Failed to obtain a valid token after authentication. Bot cannot start.")
                        # Potentially exit or wait before retrying
                        time.sleep(10) # Wait before retrying the loop
                        continue # Restart the bot loop

                # If loop was created here, run the bot in it.
                # If loop was pre-existing, tasks will be scheduled on it.
                # Pass the fetched valid_token to the TwitchBot constructor
                bot = TwitchBot(token=valid_token, 
                                config=self.config, 
                                token_manager=self.token_manager, 
                                time_blocker=self.time_blocker, 
                                command_logger=self.command_logger)
                bot.restart_event = self.restart_bot_event
                
                # The token is set during super().__init__ now.
                # If _connection needs explicit update after init, it would be:
                # bot._connection._token = valid_token 
                # However, twitchio's commands.Bot should handle this if token is passed to __init__.

                loop.run_until_complete(bot.start())

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {str(e)}")
                time.sleep(5)
            finally:
                if loop and loop.is_running():
                    loop.close()

    def run(self):
        """Run the application"""
        # Load configuration
        self.config.load()

        # Start Flask server in a separate thread
        flask_thread = threading.Thread(target=self.run_flask)
        flask_thread.daemon = True
        flask_thread.start()
        time.sleep(2)

        # Check if config is still default and wait for update if necessary
        if self.config.get('TWITCH_CLIENT_ID') == 'your_client_id':
            print("\nConfiguration is incomplete. Please access http://localhost:5000/config or https://localhost:5000/config to configure the application.\n")
            # Open config page in browser
            try:
                webbrowser.open("https://localhost:5000/config") # Prefer HTTPS
            except Exception as e:
                print(f"Could not open browser automatically: {str(e)}")


            # Wait for the configuration to be updated and the restart signal
            print("Waiting for configuration update...")
            # Use a polling loop instead of blocking wait
            while not self.app_should_restart.is_set():
                time.sleep(0.5) # Poll every 0.5 seconds

            self.app_should_restart.clear() # Clear the event for future restarts
            print("Configuration updated. Proceeding to start bot...")

        else:
            print("\nConfiguration loaded successfully. Starting bot...\n")

        # Start bot in a separate thread
        bot_thread = threading.Thread(target=self.run_bot)
        bot_thread.daemon = True
        bot_thread.start()
        # Keep the main thread alive
        try:
            while True:
                time.sleep(1) # Keep the main thread alive
        except KeyboardInterrupt:
            print("Shutting down application...")



# Global instance for Flask routes to access
app_instance = None

if __name__ == '__main__':
    app_instance = Application()
    app_instance.run()
