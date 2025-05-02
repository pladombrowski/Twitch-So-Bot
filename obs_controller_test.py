import time
import threading
from typing import Any
from obswebsocket import obsws, requests as obs_requests

class Config:
    """Simplified Config class for testing"""
    def __init__(self):
        self.config = {
            'OBS_HOST': 'localhost',
            'OBS_PORT': 4455,
            'OBS_PASSWORD': 'password'
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

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