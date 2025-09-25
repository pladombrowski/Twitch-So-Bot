import re
import aiohttp

async def play_video_from_channel_on_obs(ctx, bot, *args):
    """
    Handles the !so command logic with support for multiple channels.
    Supports formats: !so canal1 canal2 canal3 or !so canal1,canal2,canal3
    """
    if bot.time_blocker.is_command_blocked():
        await ctx.channel.send(bot.config.get_message('bot.command_blocked'))
        return

    if not args:
        await ctx.channel.send(bot.config.get_message('bot.invalid_command_format'))
        return

    # Parse channels from arguments
    channels = []
    for arg in args:
        # Split by comma if present, otherwise use the argument as is
        if ',' in arg:
            channels.extend([ch.strip() for ch in arg.split(',')])
        else:
            channels.append(arg.strip())

    # Remove empty channels and validate
    valid_channels = []
    invalid_channels = []
    
    for channel in channels:
        if channel and re.match(r'^[a-zA-Z0-9_]{4,25}$', channel):
            valid_channels.append(channel)
        elif channel:
            invalid_channels.append(channel)

    if invalid_channels:
        await ctx.channel.send(f"❌ Canais inválidos: {', '.join(invalid_channels)}")
        return

    if not valid_channels:
        await ctx.channel.send(bot.config.get_message('bot.invalid_command_format'))
        return

    # Process each valid channel
    try:
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            for i, channel_name in enumerate(valid_channels):
                try:
                    async with session.post(
                        'https://localhost:5000/play',
                        json={'channel': channel_name},
                        timeout=35
                    ) as response:
                        if response.status == 200:
                            bot.command_logger.log_command(
                                command='so',
                                channel=channel_name.lower(),
                                requester=ctx.author.name
                            )
                            response_data = await response.json()
                            queue_position = response_data.get('queue_position', 1)

                            if len(valid_channels) == 1:
                                # Single channel - use original messages
                                if queue_position > 1:
                                    await ctx.channel.send(bot.config.get_message('bot.add_to_queue', channel_name=channel_name, queue_position=queue_position))
                                else:
                                    await ctx.channel.send(bot.config.get_message('bot.playing_now', channel_name=channel_name))
                            else:
                                # Multiple channels - use custom messages
                                if queue_position > 1:
                                    await ctx.channel.send(f"📺 Canal '{channel_name}' adicionado à fila (posição {queue_position})")
                                else:
                                    await ctx.channel.send(f"🎬 Tocando canal '{channel_name}' agora!")
                        else:
                            error_msg = (await response.json()).get('error', 'Erro desconhecido')
                            await ctx.channel.send(f"❌ Erro com canal '{channel_name}': {error_msg}")
                            
                except Exception as e:
                    print(f"Error processing channel {channel_name}: {str(e)}")
                    await ctx.channel.send(f"❌ Erro ao processar canal '{channel_name}'")

            # Send summary message for multiple channels
            if len(valid_channels) > 1:
                await ctx.channel.send(f"✅ Processados {len(valid_channels)} canal(is): {', '.join(valid_channels)}")

    except Exception as e:
        print(f"Error in request: {str(e)}")
        await ctx.channel.send(bot.config.get_message('bot.internal_error'))