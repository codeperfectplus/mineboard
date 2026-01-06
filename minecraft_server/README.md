# Optional Minecraft Server Setup

## Overview
This folder contains a ready-to-use Minecraft server configuration using the popular [itzg/minecraft-server](https://github.com/itzg/docker-minecraft-server) Docker image. If you don't already have a Minecraft server running, you can use this setup to quickly deploy one alongside the control panel.

## Prerequisites
- Docker and Docker Compose installed
- At least 8GB of RAM available (12GB recommended for optimal performance)
- Port availability: 25565 (Java), 19132 (Bedrock), 25575 (RCON)

## Quick Start

### 1. Create Environment File
Create a `.env` file in this directory with the following configuration:

```bash
# Server Basic Settings
MINECRAFT_EULA=TRUE
MINECRAFT_SERVER_TYPE=PAPER
MINECRAFT_SERVER_VERSION=LATEST
MINECRAFT_SERVER_NAME=My Minecraft Server
MINECRAFT_MOTD=Welcome to my server!

# Server Configuration
MINECRAFT_DIFFICULTY=normal
MINECRAFT_MAX_PLAYERS=20
MINECRAFT_ONLINE_MODE=true

# Memory Settings
MINECRAFT_MAX_MEMORY=12G

# RCON Configuration (Important for Control Panel)
MINECRAFT_RCON_PASSWORD=your_secure_password_here
MINECRAFT_RCON_PORT=25575

# Port Mappings
MINECRAFT_JAVA_PORT=25565
MINECRAFT_BEDROCK_PORT=19132

# Data Path
MINECRAFT_DATA_PATH=./minecraft-data
```

### 2. Accept the EULA
By setting `MINECRAFT_EULA=TRUE`, you accept the [Minecraft End User License Agreement](https://www.minecraft.net/en-us/eula).

### 3. Start the Server
```bash
docker compose up -d
```

The server will start and begin downloading the necessary files on first run.

### 4. View Logs
```bash
docker compose logs -f minecraft
```

### 5. Stop the Server
```bash
docker compose down
```

## Configuration Options

### Server Types
Choose from various server types by setting `MINECRAFT_SERVER_TYPE`:
- `VANILLA` - Official Minecraft server
- `PAPER` - High-performance fork with plugins (recommended)
- `SPIGOT` - Popular plugin platform
- `FORGE` - For mod support
- `FABRIC` - Lightweight mod loader
- `PURPUR` - Paper fork with extra features

### Server Versions
Set `MINECRAFT_SERVER_VERSION` to:
- `LATEST` - Latest stable release
- `SNAPSHOT` - Latest snapshot
- `1.20.4` - Specific version number

### Difficulty Levels
`MINECRAFT_DIFFICULTY` options:
- `peaceful` - No hostile mobs
- `easy` - Reduced mob damage
- `normal` - Standard gameplay
- `hard` - Increased challenge

### Memory Allocation
Adjust `MINECRAFT_MAX_MEMORY` based on your system:
- Minimum: `4G` for small servers (1-5 players)
- Recommended: `8G` for medium servers (5-15 players)
- Optimal: `12G+` for larger servers (15+ players)

The JVM settings in docker-compose.yml are pre-tuned for performance with G1GC garbage collector.

## Connecting the Control Panel

After starting this Minecraft server, configure the control panel to connect to it:

### Option 1: Same Host (Recommended)
Update the control panel's `.env` file:
```bash
RCON_HOST=172.17.0.1  # Docker bridge IP
RCON_PORT=25575
RCON_PASSWORD=your_secure_password_here  # Must match server password
```

### Option 2: Custom Docker Network
Create a shared network:
```bash
docker network create minecraft-network
```

Update both docker-compose files to use this network, then set:
```bash
RCON_HOST=minecraft-server  # Container name
RCON_PORT=25575
RCON_PASSWORD=your_secure_password_here
```

## Included Features

### Plugins (Paper/Spigot)
The configuration includes:
- **Geyser** - Allows Bedrock players to join Java servers
- **Floodgate** - Bedrock player authentication
- **Vault** - Economy and permissions API

### Performance Optimizations
- G1 Garbage Collector tuned for low latency
- Optimized heap settings
- Parallel reference processing
- Pre-allocated memory for stability

### Cross-Play Support
Bedrock Edition players can connect via port 19132 (UDP) thanks to Geyser plugin.

## Data Persistence

Server data is stored in the directory specified by `MINECRAFT_DATA_PATH`. This includes:
- World saves
- Player data
- Server properties
- Plugin configurations
- Logs

**Important:** Back up this directory regularly to prevent data loss.

## Troubleshooting

### Server won't start
- Check Docker logs: `docker compose logs minecraft`
- Verify EULA is set to `TRUE`
- Ensure ports aren't already in use
- Check available system memory

### Control panel can't connect
- Verify RCON is enabled in server console
- Check RCON password matches in both configs
- Test connectivity: `telnet <RCON_HOST> 25575`
- Verify firewall rules allow the connection

### Poor performance
- Increase `MINECRAFT_MAX_MEMORY` if available
- Reduce `MINECRAFT_MAX_PLAYERS`
- Monitor CPU usage: `docker stats minecraft-server`
- Consider using PAPER or PURPUR server type for better performance

### Can't join the server
- Check if online mode is appropriate for your setup
- Verify port 25565 is accessible from outside
- Check server logs for connection attempts
- Ensure you're using the correct server version

## Updating the Server

### Update to Latest Version
```bash
docker compose down
docker compose pull
docker compose up -d
```

### Change Server Version
Edit `.env` and update `MINECRAFT_SERVER_VERSION`, then:
```bash
docker compose up -d --force-recreate
```

**Warning:** Backup your data before updating!

## Advanced Configuration

### Custom server.properties
Mount a custom properties file:
```yaml
volumes:
  - ${MINECRAFT_DATA_PATH}:/data
  - ./server.properties:/data/server.properties
```

### Additional Plugins
Add plugin URLs to the `PLUGINS` environment variable in docker-compose.yml.

### World Generation
Use environment variables like:
- `LEVEL_TYPE` - flat, largeBiomes, amplified, etc.
- `SEED` - Custom world seed
- `GENERATE_STRUCTURES` - true/false

See the [itzg/minecraft-server documentation](https://docker-minecraft-server.readthedocs.io/) for all options.

## Security Recommendations

1. **Change the default RCON password** - Use a strong, unique password
2. **Enable whitelist** - Set `WHITELIST=<player1>,<player2>` in `.env`
3. **Regular backups** - Automate backups of `MINECRAFT_DATA_PATH`
4. **Update regularly** - Keep server version current for security patches
5. **Firewall rules** - Only expose necessary ports
6. **Monitor logs** - Check for suspicious activity

## Support

For issues specific to:
- **Docker image**: [itzg/docker-minecraft-server](https://github.com/itzg/docker-minecraft-server/issues)
- **Control panel**: Return to the main project README
- **Minecraft server**: [Minecraft Wiki](https://minecraft.fandom.com/wiki/Server)

## License

The Minecraft server software is subject to [Mojang's EULA](https://www.minecraft.net/en-us/eula).
The Docker image is provided by itzg under the Apache 2.0 License.
