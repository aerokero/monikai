import asyncio
import socketio

async def test():
    sio = socketio.AsyncClient()
    
    @sio.event
    async def connect():
        print('[Connected to server]')
        # Manually trigger start_audio
        await sio.emit('start_audio', {
            'device_name': 'SteelSeries Sonar - Microphone',
            'device_index': 1,
            'video_mode': 'none'
        })
        print('[Emitted start_audio]')
        await asyncio.sleep(5)
        await sio.disconnect()
    
    try:
        await sio.connect('http://localhost:8000', wait_timeout=5)
    except Exception as e:
        print(f'[Connect failed] {e}')

asyncio.run(test())
