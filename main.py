import discord
from discord.ext import commands
from transformers import AutoTokenizer, AutoModel
import requests
import asyncio
import torch
import torch.nn.functional as F
import better_profanity
import os
from io import BytesIO
from captcha.image import ImageCaptcha


intents = discord.Intents.all()
intents.typing = False
bot = commands.Bot(command_prefix='!', intents=intents)

message_cooldown = commands.CooldownMapping.from_cooldown(1, 1.0, commands.BucketType.user)
recent_messages = {}
duplicate_words = {}

# Add your reCAPTCHA secret key here
RECAPTCHA_SECRET_KEY = os.getenv("6LdtaacnAAAAAF3osyJ9ZGH0RjxHEXAbfYxZYMuw")

# Load BERT model and tokenizer for semantic similarity
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
model = AutoModel.from_pretrained("bert-base-uncased")

# Initialize the captcha generator
captcha_generator = ImageCaptcha()


def is_spam_or_inappropriate(content):
    if len(set(content.split())) < len(content.split()) * 0.5:
        return True

    # Check for excessive capital letters
    if sum(1 for c in content if c.isupper()) > len(content) * 0.5:
        return True

    # Check for profanity using better_profanity
    def has_profanity(content):
        return better_profanity.check_profanity(content)["profanity"]

    return False


async def delete_message_with_delay(message, delay):
    await asyncio.sleep(delay)
    await message.delete()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} - {bot.user.id}")
    await bot.change_presence(status=discord.Status.online, activity=discord.Game(name="Guarding the server"))


def semantic_similarity(a, b):
    inputs = tokenizer([a, b], return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        outputs = model(**inputs)
    similarity = F.cosine_similarity(outputs.last_hidden_state[0], outputs.last_hidden_state[1]).mean().item()
    return similarity


@bot.event
async def on_member_join(member):
    # Generate a random captcha text
    captcha_text = "some_generated_captcha_text"

    # Generate a captcha image using the captcha generator
    captcha_image = captcha_generator.generate(captcha_text)
    captcha_io = BytesIO()
    captcha_image.save(captcha_io, format='PNG')
    captcha_io.seek(0)

    # Send captcha verification with reCAPTCHA
    embed = discord.Embed(title="Captcha Verification", description="Please complete the reCAPTCHA to join the server.")
    embed.set_image(url="attachment://captcha.png")
    await member.send(embed=embed, file=discord.File(captcha_io, filename='captcha.png'))

    def check_captcha(response):
        return (
                member == response.author
                and response.channel == member.dm_channel
                and response.content == captcha_text
        )

    try:
        captcha_response = await bot.wait_for("message", check=check_captcha, timeout=60)
        if captcha_response:
            # Perform reCAPTCHA verification here
            user_response = captcha_response.content
            verification_payload = {
                "secret": RECAPTCHA_SECRET_KEY,
                "response": user_response
            }
            response = requests.post("https://www.google.com/recaptcha/api/siteverify", data=verification_payload)
            result = response.json()

            if result.get("success"):
                await member.send("Captcha verification successful. Welcome to the server!")
                # Add the user to the server or assign roles here
            else:
                await member.send("Captcha verification failed. Please try again later.")
    except asyncio.TimeoutError:
        await member.send("Captcha verification timed out. Please try again later.")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if is_spam_or_inappropriate(message.content):
        await message.delete()
        warning_message = await message.channel.send(
            f"{message.author.mention}, your message contains spam or inappropriate content.")
        await delete_message_with_delay(warning_message, 10)

    bucket = message_cooldown.get_bucket(message)
    if bucket.update_rate_limit():
        await message.delete()
        warning_message = await message.channel.send(f"{message.author.mention}, you're sending messages too quickly.")
        await delete_message_with_delay(warning_message, 10)

    await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return


bot.run('your-token-here')
