# Minecraft Server Control

## What this is
Self-hosted Flask dashboard to control a running Minecraft server over RCON. It wraps common admin tasks (teleport, give items, run kits, quick gamerule toggles, whitelist/op, weather/time, locate villages) behind a web UI and a small REST API.

## Why I built it
- Make everyday admin chores fast without typing long commands in-game.
- Give non-technical friends a safe, focused control panel instead of full console access.
- Centralize common presets (kits, locations) so they are repeatable and shareable.
- Runable in a container alongside the itzg/minecraft-server image with minimal setup.

## High-level architecture
- Flask app (this repo) exposes UI + JSON endpoints.
- RCON client (mcrcon library) reuses a single connection to the Minecraft server.
- SQLite stores saved locations; JSON files store kits/config seeds.
- Docker Compose can run the web app and mount persistent data at `/app/data`.

## Quick start
1) Set environment in `.env` (example when the server is reachable on the host bridge):
	- `RCON_HOST=172.17.0.1`
	- `RCON_PORT=25575`
	- `RCON_PASSWORD=<your_rcon_password>`
2) Bring up the web app:
	- `docker compose up -d --force-recreate web`
3) Open the dashboard at `http://localhost:5090`.
4) Use `GET /api/test-connection` to confirm RCON connectivity.

## Notes
- Ensure your Minecraft server has `enable-rcon=true` and the password matches `.env`.
- If you run both containers on a custom Docker network, set `RCON_HOST` to the Minecraft container name instead of the bridge IP.
