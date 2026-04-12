import asyncio
import socketio
import time

async def test():
    sio = socketio.AsyncClient()
    
    @sio.event
    async def connect():
        print('[✓ Connected to backend]')
        await sio.emit('get_settings')
        print('[✓ Emitted get_settings]')
        await asyncio.sleep(1)
        await sio.emit('start_audio', {
            'device_name': 'SteelSeries Sonar - Microphone',
            'device_index': 1,
            'video_mode': 'none'
        })
        print('[✓ Emitted start_audio]')
        await asyncio.sleep(10)
    
    @sio.event
    async def disconnect():
        print('[✗ Disconnected]')
    
    try:
        await sio.connect('http://localhost:8000', wait_timeout=5)
        # Keep connection alive
        while sio.connected:
            await asyncio.sleep(1)
    except Exception as e:
        print(f'[✗ Connect error] {e}')

asyncio.run(test())
