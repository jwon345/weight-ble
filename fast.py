import asyncio
import logging
import datetime

import supabase
import datetime
import dotenv
import os

from pathlib import Path

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

dotenv.load_dotenv()

BODY_COMPOSITION_MEASUREMENT_UUID = "00002a9d-0000-1000-8000-00805f9b34fb"
SCALE_NAME = "MI SCALE2"
ADDR_FILE = Path("./miscale_addr.txt")
DATA_FILE = Path("./weight.csv")

SWING_RANGE = 5
LAST_WEIGH_PATH = Path("./last_weight.txt")

logger = logging.getLogger(__name__)

KEY = os.environ.get("SUPA_KEY")
URL = os.environ.get("SUPA_URL")

client : supabase.Client = supabase.create_client(URL,KEY)

def notification_handler(ch: BleakGATTCharacteristic, data: bytearray):
    flags = int.from_bytes(data[0:2], "little")
    weight = int.from_bytes(data[1:3], "little") / 200
    stable = bool(flags & (1 << 5))

    if stable and weight > 10:
        logger.info(f"weight: {weight:.2f} kg (stable) @ {datetime.datetime.now()}")

        if not LAST_WEIGH_PATH.exists():
            logger.error("No last weight file found, creating one.")
            LAST_WEIGH_PATH.write_text(str(weight))

        # Check what the last weight was
        last_weight = float(LAST_WEIGH_PATH.read_text().strip())
        if abs(weight - last_weight) <= SWING_RANGE:
            with DATA_FILE.open("a") as f:
                f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{weight:.2f}\n")
            with LAST_WEIGH_PATH.open("w") as f:
                f.write(f"{weight:.2f}")
            (client.table("weight").insert({"time":datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "weight":f"{weight:.2f}" }).execute())
        else:
            logger.info(f"Weight change {abs(weight - last_weight):.2f} kg exceeds swing range of {SWING_RANGE} kg. Not logging.")
            

async def get_or_find_device_address() -> str:
    if ADDR_FILE.exists():
        return ADDR_FILE.read_text().strip()

    # One short scan to learn the address; then persist it
    logger.info("Scanning briefly to find device address...")
    devices = await BleakScanner.discover(timeout=1.0)
    for d in devices:
        if d.name == SCALE_NAME:
            ADDR_FILE.write_text(d.address)
            logger.info(f"Cached {SCALE_NAME} address: {d.address}")
            return d.address

    # Fallback targeted search with a short timeout
    dev = await BleakScanner().find_device_by_name(SCALE_NAME, timeout=3.0)
    if not dev:
        raise RuntimeError(f"Could not find {SCALE_NAME}. Is it awake/advertising?")
    ADDR_FILE.write_text(dev.address)
    logger.info(f"Cached {SCALE_NAME} address: {dev.address}")
    return dev.address

async def connect_and_stream(address: str):
    disconnected_event = asyncio.Event()

    def on_disconnect(_client: BleakClient):
        logger.info("Disconnected.")
        disconnected_event.set()

    async with BleakClient(address, disconnected_callback=on_disconnect) as client:
        logger.info(f"Connected to {address}. Enabling notify...")
        await client.start_notify(BODY_COMPOSITION_MEASUREMENT_UUID, notification_handler)
        logger.info("Notify started. Waiting for data...")
        await disconnected_event.wait()

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)-15s %(name)-8s %(levelname)s: %(message)s",
    )
    addr = None
    while not addr: 
        try:
            addr = await get_or_find_device_address()
        except Exception as e:
            logger.info(f"Error finding device: {e!r}")

    # Fast reconnect loop without rescanning
    backoff = 0.1
    while True:
        try:
            await connect_and_stream(addr)
            # If we get here, a disconnect happened — try fast reconnect
        except Exception as e:
            logger.info(f"Connect error: {e!r}")
        await asyncio.sleep(backoff)
        # backoff = min(backoff * 2, 5.0)  # cap backoff

if __name__ == "__main__":
    asyncio.run(main())
