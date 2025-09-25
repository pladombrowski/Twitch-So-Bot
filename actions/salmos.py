import aiohttp
import asyncio
import time
import threading
import random
import subprocess
import os
import tempfile
from obswebsocket import obsws, requests as obs_requests

async def play_phrase_as_audio_on_obs(ctx, bot, *args):
    """
    Handles the !salmos command logic - generates a psalm using Ollama and plays as audio.
    """
    if bot.time_blocker.is_command_blocked():
        await ctx.channel.send(bot.config.get_message('bot.command_blocked'))
        return

    if not args:
        await ctx.channel.send(bot.config.get_message('bot.invalid_command_format'))
        return
    
    # Join all arguments into a single phrase
    phrase = ' '.join(args)

    try:
        # Log the command
        bot.command_logger.log_command(
            command='salmos',
            channel=ctx.channel.name,
            requester=ctx.author.name
        )

        await ctx.channel.send(f"🎵 Gerando salmo para: '{phrase}'...")
        
        # Generate psalm using AI service (Ollama or LM Studio)
        psalm_text = await generate_psalm_with_ai(phrase)
        
        if not psalm_text:
            await ctx.channel.send("❌ Erro ao gerar salmo. Tente novamente.")
            return
        
        # Add author and verse info
        author_name = ctx.author.name
        psalm_number = random.randint(1, 99)
        verse_number = random.randint(1, 99)
        
        final_text = f"{psalm_text}, {author_name}, salmo {psalm_number}, versículo {verse_number}, amém!"
        
        await ctx.channel.send(f"📖 Salmo gerado! Reproduzindo...")
        
        # Generate and play audio in OBS (like !so command)
        audio_duration = await generate_and_play_audio_in_obs(final_text)
        
        if audio_duration > 0:
            # Send the psalm text to chat
            await ctx.channel.send(f"📖 **Salmo:** {final_text}")
        else:
            await ctx.channel.send("❌ Erro ao gerar áudio do salmo.")
        
    except Exception as e:
        print(f"Error in salmos command: {str(e)}")
        await ctx.channel.send(bot.config.get_message('bot.internal_error'))

async def generate_psalm_with_ai(phrase: str):
    """
    Generate a psalm using Ollama or LM Studio with OpenAI-compatible API.
    """
    try:
        prompt = f"Reescreva a frase a seguir no estilo da Bíblia. Responda APENAS com uma frase reescrita, sem introduções ou explicações. Frase: {phrase}"
        
        # Try Ollama first (OpenAI-compatible endpoint)
        result = await try_ollama_openai_api(prompt)
        if result:
            return result
        
        # Try LM Studio (OpenAI-compatible endpoint)
        result = await try_lm_studio_openai_api(prompt)
        if result:
            return result
        
        # Fallback to direct Ollama API
        result = await try_ollama_direct_api(prompt)
        if result:
            return result
            
        print("No AI service available")
        return None
                    
    except Exception as e:
        print(f"Error calling AI service: {str(e)}")
        return None

async def try_ollama_openai_api(prompt: str):
    """
    Try Ollama with OpenAI-compatible API endpoint.
    """
    try:
        ollama_url = "http://localhost:11434/v1/chat/completions"
        
        payload = {
            "model": "llama4",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 200,
            "temperature": 0.7
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(ollama_url, json=payload, timeout=60) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
                else:
                    print(f"Ollama OpenAI API error: {response.status}")
                    return None
                    
    except Exception as e:
        print(f"Ollama OpenAI API error: {str(e)}")
        return None

async def try_lm_studio_openai_api(prompt: str):
    """
    Try LM Studio with OpenAI-compatible API endpoint.
    """
    try:
        lm_studio_url = "http://localhost:1234/v1/chat/completions"
        
        payload = {
            "model": "local-model",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 200,
            "temperature": 0.7
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(lm_studio_url, json=payload, timeout=60) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
                else:
                    print(f"LM Studio API error: {response.status}")
                    return None
                    
    except Exception as e:
        print(f"LM Studio API error: {str(e)}")
        return None

async def try_ollama_direct_api(prompt: str):
    """
    Try Ollama with direct API endpoint (fallback).
    """
    try:
        ollama_url = "http://localhost:11434/api/generate"
        
        payload = {
            "model": "llama4",
            "prompt": prompt,
            "stream": False
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(ollama_url, json=payload, timeout=60) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('response', '').strip()
                else:
                    print(f"Ollama direct API error: {response.status}")
                    return None
                    
    except Exception as e:
        print(f"Ollama direct API error: {str(e)}")
        return None

async def generate_and_play_audio_in_obs(text: str):
    """
    Generate audio from text using TTS and play it in OBS (like !so command).
    """
    try:
        # Create temporary file for audio
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            temp_audio_path = temp_file.name
        
        # Try espeak-ng first (faster, local)
        audio_duration = await try_espeak_tts(text, temp_audio_path)
        
        if audio_duration == 0:
            # Fallback to gTTS (Google Text-to-Speech)
            print("espeak-ng not available, trying gTTS...")
            audio_duration = await try_gtts_tts(text, temp_audio_path)
        
        if audio_duration > 0:
            # Play audio in OBS via HTTP request (like !so command)
            await play_audio_via_http(temp_audio_path, audio_duration)
            
            # Clean up temporary file after delay
            threading.Thread(
                target=cleanup_audio_file,
                args=(temp_audio_path, audio_duration),
                daemon=True
            ).start()
                
            return audio_duration
        else:
            print("All TTS methods failed")
            return 0
            
    except Exception as e:
        print(f"Error generating audio: {str(e)}")
        return 0

def cleanup_audio_file(audio_path: str, delay: float):
    """Clean up audio file after delay"""
    try:
        import time
        time.sleep(delay + 2)  # Wait for audio to finish + buffer
        os.unlink(audio_path)
        print(f"Audio file cleaned up: {audio_path}")
    except Exception as e:
        print(f"Error cleaning up audio file: {str(e)}")

async def try_espeak_tts(text: str, output_path: str):
    """
    Try to generate audio using espeak-ng.
    """
    try:
        import platform
        
        # Check if espeak-ng is available
        system = platform.system().lower()
        
        if system == "windows":
            # On Windows, try different possible locations
            possible_paths = [
                'espeak-ng',
                'espeak',
                r'C:\Program Files\espeak-ng\espeak-ng.exe',
                r'C:\Program Files (x86)\espeak-ng\espeak-ng.exe'
            ]
            
            espeak_cmd = None
            for path in possible_paths:
                try:
                    result = subprocess.run([path, '--version'], capture_output=True, timeout=5)
                    if result.returncode == 0:
                        espeak_cmd = path
                        break
                except:
                    continue
            
            if not espeak_cmd:
                print("espeak-ng not found on Windows")
                return 0
        else:
            espeak_cmd = 'espeak-ng'
        
        cmd = [
            espeak_cmd,
            '-v', 'pt-br',  # Portuguese Brazilian voice
            '-s', '150',    # Speed
            '-p', '50',     # Pitch
            '-a', '200',    # Amplitude
            '-w', output_path,
            text
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and os.path.exists(output_path):
            return get_audio_duration(output_path)
        else:
            print(f"espeak-ng error: {result.stderr}")
            return 0
            
    except Exception as e:
        print(f"espeak-ng error: {str(e)}")
        return 0

async def try_gtts_tts(text: str, output_path: str):
    """
    Try to generate audio using Google Text-to-Speech.
    """
    try:
        from gtts import gTTS
        
        print(f"Generating audio with gTTS for text: '{text[:50]}...'")
        
        # Create gTTS object
        tts = gTTS(text=text, lang='pt-br', slow=False)
        
        # Save to temporary file
        tts.save(output_path)
        
        # Check if file was created and has content
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            print(f"gTTS audio file created: {output_path} ({file_size} bytes)")
            
            if file_size > 0:
                return get_audio_duration(output_path)
            else:
                print("gTTS generated empty file")
                return 0
        else:
            print("gTTS failed to create file")
            return 0
            
    except ImportError:
        print("gTTS not available - install with: pip install gTTS")
        return 0
    except Exception as e:
        print(f"gTTS error: {str(e)}")
        return 0

def get_audio_duration(audio_path: str):
    """
    Get the duration of an audio file in seconds.
    """
    try:
        # Check if file exists and has content
        if not os.path.exists(audio_path):
            print(f"Audio file not found: {audio_path}")
            return 5
        
        file_size = os.path.getsize(audio_path)
        if file_size == 0:
            print(f"Audio file is empty: {audio_path}")
            return 5
        
        print(f"Audio file found: {audio_path} ({file_size} bytes)")
        
        # Try ffprobe first
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-show_entries', 'format=duration',
                '-of', 'csv=p=0',
                audio_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout.strip():
                duration = float(result.stdout.strip())
                print(f"Audio duration from ffprobe: {duration} seconds")
                return duration
        except Exception as e:
            print(f"ffprobe not available: {str(e)}")
        
        # Fallback: estimate duration based on file size
        # For WAV files: roughly 1KB per second, for MP3: much more compressed
        if audio_path.endswith('.wav'):
            estimated_duration = max(3, min(file_size / 1000, 30))
        else:
            # For other formats, be more conservative
            estimated_duration = max(3, min(file_size / 500, 30))
        
        print(f"Estimated audio duration: {estimated_duration} seconds")
        return estimated_duration
            
    except Exception as e:
        print(f"Error getting audio duration: {str(e)}")
        # Fallback: return a reasonable default
        return 5

# Removed OBS audio functions - now using desktop audio only to avoid duplication

# Removed OBS text source functions - now using chat instead

async def play_audio_on_desktop(text: str, duration: float):
    """
    Play audio directly on the desktop so the streamer can hear it.
    """
    try:
        # Create temporary audio file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            temp_audio_path = temp_file.name
        
        # Generate audio using TTS
        audio_duration = await try_espeak_tts(text, temp_audio_path)
        
        if audio_duration == 0:
            audio_duration = await try_gtts_tts(text, temp_audio_path)
        
        if audio_duration > 0 and os.path.exists(temp_audio_path):
            # Play audio on desktop using system audio player
            await play_audio_file_on_desktop(temp_audio_path)
            
            # Clean up temporary file
            try:
                os.unlink(temp_audio_path)
            except:
                pass
                
            return audio_duration
        else:
            return 0
            
    except Exception as e:
        print(f"Error playing audio on desktop: {str(e)}")
        return 0

async def play_audio_via_http(audio_path: str, duration: float):
    """
    Play audio via HTTP request to Flask app (like !so command).
    """
    try:
        import aiohttp
        
        if not os.path.exists(audio_path):
            print(f"Audio file not found: {audio_path}")
            return
        
        print(f"Playing audio via HTTP: {audio_path}")
        
        # Make HTTP request to Flask app
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                'https://localhost:5000/play_audio',
                json={
                    'audio_path': audio_path,
                    'duration': duration
                },
                timeout=35
            ) as response:
                if response.status == 200:
                    print("Audio playback started successfully via HTTP")
                else:
                    error_msg = (await response.json()).get('error', 'Erro desconhecido')
                    print(f"Error playing audio via HTTP: {error_msg}")
                    
    except Exception as e:
        print(f"Error playing audio via HTTP: {str(e)}")
