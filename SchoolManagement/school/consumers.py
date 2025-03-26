import json
from channels.generic.websocket import AsyncWebsocketConsumer

class AttendanceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Runs when a client connects to the WebSocket."""
        await self.channel_layer.group_add("attendance_updates", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        """Runs when a client disconnects from the WebSocket."""
        await self.channel_layer.group_discard("attendance_updates", self.channel_name)

    async def send_attendance_update(self, event):
        """Sends real-time attendance updates to clients."""
        await self.send(text_data=json.dumps(event["student"]))
