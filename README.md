<div align = center>
  <img src="imgs/logo.png" width="200" height="200">

    
discord-style matrix.org API wrapper for Python 
<br>
</div>

# how to install

```
pip install trixc
```

# example

```py
import trixc

bot = trixc.Bot(
    homeserver="https://matrix.org",
    command_prefix="!",
    description="My first trixc bot",
)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user.id}")


@bot.command(aliases=["p"])
@trixc.cooldown(1, 3.0)
async def ping(ctx):
    """Check if the bot is alive."""
    await ctx.reply("🏓 Pong!")

bot.run("@bot:homeserver.org", "password")
```

# if you want to build a bot using this library - go read the source code. there is no official documentation, and there might never be. the codebase is designed to be intuitive for anyone familiar with discord.py/disnake, so the best way to learn is to explore the code yourself.
