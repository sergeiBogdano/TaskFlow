"""Process guard; the durable queue also holds a cross-process database lease."""
import asyncio

ollama_lock = asyncio.Lock()
