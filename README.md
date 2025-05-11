# Twitch SO Bot (Shoutout Bot)

[Leia em Português (Read in Portuguese)](README.pt-br.md)

A Twitch bot that displays random clips, videos, or highlights from specified channels without relying on third-party services. The bot integrates with OBS to automatically show content when authorized users run the `!so` command in your Twitch chat.

## Features

- Displays random clips, videos, or highlights from any Twitch channel
- Integrates directly with OBS via WebSocket
- Customizable content types (clips, videos, highlights)
- Time-based command blocking
- User authorization system
- Command usage logging
- Web-based configuration interface

## Requirements

- [OBS Studio](https://obsproject.com/) with WebSocket plugin enabled
- Twitch account
- Twitch Developer Application

## Installation

1. Download the latest release of `so_bot.exe` from [GitHub Releases](https://github.com/pladombrowski/so_bot/releases)
2. Run the executable on your computer
3. The application will open a browser window for Twitch authentication
4. After authentication, access the configuration page at http://localhost:5000/config

## Setup

### Twitch Developer Application

1. Go to [Twitch Developer Console](https://dev.twitch.tv/)
2. Register a new application
3. Choose a name for your application
4. In the "OAuth Redirect URLs" field, enter:
   ```
   http://localhost:5000/auth/callback
   ```
5. Set the category to "Chat Bot"
6. Complete the CAPTCHA and save
7. Copy the "Client ID" and "Client Secret" for configuration

### OBS WebSocket Setup

1. In OBS, go to Tools > WebSocket Server Settings
2. Check "Enable WebSocket Server"
3. Click "Show Connection Info" to view your password
4. Note the server, port, and password for configuration

### Bot Configuration

1. Access the configuration page at http://localhost:5000/config
2. Enter your Twitch Client ID and Client Secret
3. Enter your OBS WebSocket connection details
4. Set the maximum video duration (in seconds)
5. Add authorized users who can run the `!so` command (comma-separated)
6. Configure the time period when commands should be blocked (if desired)
7. Select the content types you want to display (clips, videos, highlights)
8. Click "Save Settings" to apply your configuration and start the bot

## Usage

Once configured, authorized users can use the following command in your Twitch chat:

```
!so channel_name
```

This will search for content from the specified channel and display a random clip, video, or highlight in your OBS scene.

## Troubleshooting

- Make sure OBS is running with the WebSocket server enabled
- Verify that your Twitch Developer Application credentials are correct
- Check that you have a scene named "Twitch Auto" in your OBS setup
- Ensure the bot has proper authorization by checking the tokens.yaml file

## Dependencies

- requests
- Flask
- flask-cors
- PyYAML
- twitchio
- obs-websocket-py
- asqlite

## License

This project is available as open source under the terms of the MIT License.