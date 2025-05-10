# -*- coding: utf-8 -*-
# main_bot.py

import discord
from discord.ext import commands
import yt_dlp # ใช้ yt-dlp แทน youtube_dl เพราะมีการอัปเดตสม่ำเสมอ
import asyncio
import logging

# ตั้งค่า logging เพื่อดู error (ถ้ามี)
logging.basicConfig(level=logging.INFO)

# Token ของบอทคุณ (สำคัญมาก: ให้เก็บเป็นความลับ)
# แนะนำให้ใช้ environment variable หรือ config file ในการเก็บ token จริง
BOT_TOKEN = "MTI5MzE0NDgwMjQ4NTA3NjAzOQ.GCI0Q6.tvf9wDnauQgWC88qXv18zY_WRjQHGz0b_jRQqc" 

# ตั้งค่า Intents (สิทธิ์ที่บอทต้องการ)
intents = discord.Intents.default()
intents.message_content = True # จำเป็นสำหรับการอ่านเนื้อหาข้อความ (คำสั่ง)
intents.voice_states = True    # จำเป็นสำหรับการจัดการสถานะเสียง

# Prefix ของคำสั่ง
bot = commands.Bot(command_prefix="#", intents=intents) # <--- เปลี่ยน prefix ตรงนี้

# การตั้งค่าสำหรับ yt-dlp และ ffmpeg
YDL_OPTIONS = {
    'format': 'bestaudio/best', # เลือกคุณภาพเสียงที่ดีที่สุด
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,        # ถ้าเป็น URL ของ playlist จะไม่โหลดทั้ง playlist (ยกเว้นจะระบุ)
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch', # ค้นหาบน YouTube โดยอัตโนมัติถ้าไม่ได้ใส่ URL
    'source_address': '0.0.0.0'  # ป้องกันปัญหา IPv6
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', # ช่วยให้การเชื่อมต่อเสถียรขึ้น
    'options': '-vn' # ไม่เอาส่วนวิดีโอ เอาแต่เสียง
}

# Dictionary สำหรับเก็บคิวเพลงของแต่ละเซิร์ฟเวอร์ (guild)
queues = {} # {guild_id: [song_info, song_info, ...]}

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def play_next_song(self, ctx):
        """
        เล่นเพลงถัดไปในคิวของเซิร์ฟเวอร์ (guild) นั้นๆ
        """
        guild_id = ctx.guild.id
        if guild_id in queues and queues[guild_id]:
            # ถ้ามีเพลงในคิว
            voice_client = ctx.guild.voice_client
            if voice_client and voice_client.is_connected():
                song_info = queues[guild_id].pop(0) # เอาเพลงแรกออกจากคิว
                source_url = song_info['source']
                title = song_info['title']
                webpage_url = song_info['webpage_url']
                requester = song_info['requester']

                try:
                    # สร้าง audio source จาก ffmpeg
                    player = discord.FFmpegPCMAudio(source_url, **FFMPEG_OPTIONS)
                    
                    # ฟังก์ชันที่จะถูกเรียกเมื่อเพลงเล่นจบ
                    def after_playing(error):
                        if error:
                            logging.error(f"เกิดข้อผิดพลาดระหว่างเล่นเพลง: {error}")
                        
                        # สร้าง task ใหม่เพื่อเรียก play_next_song ใน event loop ของ bot
                        # เพื่อหลีกเลี่ยงปัญหา blocking หรือ context ที่ไม่ถูกต้อง
                        fut = asyncio.run_coroutine_threadsafe(self.play_next_song(ctx), self.bot.loop)
                        try:
                            fut.result()
                        except Exception as e:
                            logging.error(f"เกิดข้อผิดพลาดในการเรียก play_next_song: {e}")

                    voice_client.play(player, after=after_playing)
                    
                    embed = discord.Embed(
                        title="🎧 กำลังเล่นเพลง",
                        description=f"[{title}]({webpage_url})",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="ขอโดย", value=requester, inline=False)
                    embed.set_thumbnail(url=song_info.get('thumbnail', ''))
                    await ctx.send(embed=embed)
                    
                    # เก็บข้อมูลเพลงที่กำลังเล่น (สำหรับคำสั่ง nowplaying)
                    if guild_id not in self.bot.current_song:
                        self.bot.current_song[guild_id] = {}
                    self.bot.current_song[guild_id] = song_info

                except Exception as e:
                    logging.error(f"ไม่สามารถเล่นเพลงได้: {e}")
                    await ctx.send(f"😥 ไม่สามารถเล่นเพลง `{title}` ได้: {e}")
                    # ลองเล่นเพลงถัดไปถ้ามีข้อผิดพลาด
                    await self.play_next_song(ctx)
            else:
                # ถ้า voice client ไม่ได้เชื่อมต่อแล้ว (อาจจะโดนเตะ)
                if guild_id in queues:
                    queues[guild_id].clear() # ล้างคิวของเซิร์ฟเวอร์นี้
                if guild_id in self.bot.current_song:
                    del self.bot.current_song[guild_id] # ลบเพลงที่กำลังเล่นอยู่
        else:
            # ถ้าคิวหมด
            if guild_id in self.bot.current_song:
                 del self.bot.current_song[guild_id] # ลบเพลงที่กำลังเล่นอยู่
            await ctx.send("🎵 คิวเพลงหมดแล้วจ้า")
            # อาจจะเพิ่มการ disconnect หลังจากหมดคิวสักพัก

    @commands.command(name="play", aliases=["p", "เล่น"], help="เล่นเพลงจาก YouTube หรือ URL (เช่น #play Never Gonna Give You Up)")
    async def play(self, ctx, *, search_query: str):
        """
        คำสั่งสำหรับเล่นเพลง
        #play <ชื่อเพลง/URL>
        """
        guild_id = ctx.guild.id

        # 1. ตรวจสอบว่าผู้ใช้อยู่ในช่องเสียงหรือไม่
        if not ctx.author.voice:
            await ctx.send("🤔 คุณต้องอยู่ในช่องเสียงก่อนถึงจะใช้คำสั่งนี้ได้นะ")
            return

        voice_channel = ctx.author.voice.channel

        # 2. เชื่อมต่อเข้าช่องเสียงถ้ายังไม่ได้เชื่อมต่อ หรือย้ายช่องถ้าบอทอยู่ช่องอื่น
        voice_client = ctx.guild.voice_client
        if not voice_client:
            await voice_channel.connect()
            voice_client = ctx.guild.voice_client # อัปเดต voice_client instance
            await ctx.send(f"🔊 เข้าร่วมช่อง `{voice_channel.name}` แล้วจ้า")
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)
            await ctx.send(f"🔄 ย้ายไปที่ช่อง `{voice_channel.name}` แล้วจ้า")

        # 3. ค้นหาเพลง/ดึงข้อมูลเพลง
        await ctx.send(f"🔎 กำลังค้นหา `{search_query}`...")
        try:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                # ถ้า search_query ไม่ใช่ URL, yt_dlp จะใช้ default_search (ytsearch)
                # ถ้าเป็น URL, มันจะพยายามดึงข้อมูลจาก URL นั้นโดยตรง
                info = ydl.extract_info(search_query, download=False) 

                if 'entries' in info: # ถ้าเป็น playlist หรือผลการค้นหาหลายรายการ
                    # เอาวิดีโอแรกสุด
                    if info['entries']:
                        song_data = info['entries'][0]
                    else:
                        await ctx.send(f"😭 ไม่พบผลลัพธ์สำหรับ `{search_query}`")
                        return
                else: # ถ้าเป็นวิดีโอเดียว
                    song_data = info
                
                stream_url = song_data['url'] # URL ของ audio stream โดยตรง
                title = song_data.get('title', 'ไม่ทราบชื่อเพลง')
                webpage_url = song_data.get('webpage_url', '#')
                thumbnail_url = song_data.get('thumbnail', '')
                duration = song_data.get('duration', 0)
                requester = ctx.author.mention

                song_info = {
                    'source': stream_url,
                    'title': title,
                    'webpage_url': webpage_url,
                    'thumbnail': thumbnail_url,
                    'duration': duration,
                    'requester': requester
                }

        except Exception as e:
            logging.error(f"เกิดข้อผิดพลาดกับ yt-dlp: {e}")
            await ctx.send(f"😥 อ๊ะ! มีบางอย่างผิดพลาดในการค้นหาหรือดึงข้อมูลเพลง: {e}")
            return

        # 4. เพิ่มเพลงเข้าคิว
        if guild_id not in queues:
            queues[guild_id] = []
        queues[guild_id].append(song_info)

        embed = discord.Embed(
            title="🎶 เพิ่มเข้าคิวแล้ว",
            description=f"[{title}]({webpage_url})",
            color=discord.Color.green()
        )
        embed.add_field(name="ขอโดย", value=requester)
        embed.set_thumbnail(url=thumbnail_url)
        if duration:
            m, s = divmod(duration, 60)
            h, m = divmod(m, 60)
            duration_str = f"{int(h):02d}:{int(m):02d}:{int(s):02d}" if h else f"{int(m):02d}:{int(s):02d}"
            embed.add_field(name="ความยาว", value=duration_str)
        
        await ctx.send(embed=embed)

        # 5. ถ้าไม่ได้เล่นเพลงอยู่ ก็เริ่มเล่นเพลง
        if not voice_client.is_playing() and not voice_client.is_paused():
            await self.play_next_song(ctx)

    @commands.command(name="skip", aliases=["s", "ข้าม"], help="ข้ามเพลงปัจจุบัน")
    async def skip(self, ctx):
        """
        คำสั่งสำหรับข้ามเพลง
        #skip
        """
        voice_client = ctx.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            await ctx.send("🤔 ไม่มีเพลงกำลังเล่นอยู่นะ")
            return

        # หยุดเพลงปัจจุบัน (การเรียก stop() จะ trigger 'after' callback ซึ่งจะเล่นเพลงถัดไป)
        voice_client.stop()
        await ctx.send("⏭️ ข้ามเพลงปัจจุบันแล้วจ้า")
        # play_next_song จะถูกเรียกโดยอัตโนมัติจาก after_playing callback

    @commands.command(name="queue", aliases=["q", "คิว"], help="แสดงคิวเพลงปัจจุบัน")
    async def queue_command(self, ctx):
        """
        คำสั่งสำหรับแสดงคิวเพลง
        #queue
        """
        guild_id = ctx.guild.id
        
        if guild_id not in queues or not queues[guild_id]:
            await ctx.send("썰 คิวเพลงว่างเปล่าจ้า ลองใช้ `#play` เพื่อเพิ่มเพลงดูสิ") # แก้ไขตัวอย่าง prefix
            return

        embed = discord.Embed(title="รายการคิวเพลง 📜", color=discord.Color.orange())
        
        # แสดงเพลงที่กำลังเล่น (ถ้ามี)
        if guild_id in self.bot.current_song and self.bot.current_song[guild_id]:
            current = self.bot.current_song[guild_id]
            embed.add_field(
                name="กำลังเล่นอยู่ 🎧", 
                value=f"[{current['title']}]({current['webpage_url']}) (ขอโดย: {current['requester']})", 
                inline=False
            )
        
        # แสดงเพลงในคิว
        queue_list_str = ""
        for i, song in enumerate(queues[guild_id][:10]): # แสดงแค่ 10 เพลงแรกในคิว
            queue_list_str += f"{i+1}. [{song['title']}]({song['webpage_url']}) (ขอโดย: {song['requester']})\n"
        
        if not queue_list_str:
            queue_list_str = "ไม่มีเพลงในคิวถัดไป"

        embed.add_field(name="เพลงถัดไป ⏳", value=queue_list_str, inline=False)
        
        if len(queues[guild_id]) > 10:
            embed.set_footer(text=f"และอีก {len(queues[guild_id]) - 10} เพลงในคิว...")
            
        await ctx.send(embed=embed)

    @commands.command(name="stop", aliases=["หยุด"], help="หยุดเล่นเพลงและล้างคิว")
    async def stop(self, ctx):
        """
        คำสั่งสำหรับหยุดเล่นเพลงและล้างคิว
        #stop
        """
        guild_id = ctx.guild.id
        voice_client = ctx.guild.voice_client

        if voice_client and voice_client.is_connected():
            voice_client.stop() # หยุดเล่นเพลง
            if guild_id in queues:
                queues[guild_id].clear() # ล้างคิว
            if guild_id in self.bot.current_song:
                del self.bot.current_song[guild_id] # ลบเพลงที่กำลังเล่น
            await ctx.send("🛑 หยุดเล่นเพลงและล้างคิวเรียบร้อยแล้ว")
        else:
            await ctx.send("🤔 บอทไม่ได้เชื่อมต่อกับช่องเสียงใดๆ หรือไม่ได้กำลังเล่นเพลงอยู่")

    @commands.command(name="leave", aliases=["dc", "ออก"], help="ให้บอทออกจากช่องเสียง")
    async def leave(self, ctx):
        """
        คำสั่งสำหรับให้บอทออกจากช่องเสียง
        #leave
        """
        guild_id = ctx.guild.id
        voice_client = ctx.guild.voice_client

        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()
            if guild_id in queues:
                queues[guild_id].clear() # ล้างคิวเมื่อออกจากห้อง
            if guild_id in self.bot.current_song:
                del self.bot.current_song[guild_id]
            await ctx.send("👋 แล้วเจอกันใหม่นะ!")
        else:
            await ctx.send("🤔 บอทไม่ได้อยู่ในช่องเสียงใดๆ เลยนะ")
            
    @commands.command(name="nowplaying", aliases=["np", "กำลังเล่น"], help="แสดงเพลงที่กำลังเล่นอยู่")
    async def nowplaying(self, ctx):
        """
        คำสั่งสำหรับแสดงเพลงที่กำลังเล่นอยู่
        #nowplaying
        """
        guild_id = ctx.guild.id
        voice_client = ctx.guild.voice_client

        if not voice_client or not voice_client.is_playing():
            await ctx.send("🤔 ไม่มีเพลงกำลังเล่นอยู่นะ")
            return

        if guild_id in self.bot.current_song and self.bot.current_song[guild_id]:
            current = self.bot.current_song[guild_id]
            embed = discord.Embed(
                title="🎧 กำลังเล่นเพลง",
                description=f"[{current['title']}]({current['webpage_url']})",
                color=discord.Color.purple()
            )
            embed.add_field(name="ขอโดย", value=current['requester'], inline=True)
            if current.get('duration'):
                m, s = divmod(current['duration'], 60)
                h, m = divmod(m, 60)
                duration_str = f"{int(h):02d}:{int(m):02d}:{int(s):02d}" if h else f"{int(m):02d}:{int(s):02d}"
                embed.add_field(name="ความยาว", value=duration_str, inline=True)
            embed.set_thumbnail(url=current.get('thumbnail', ''))
            await ctx.send(embed=embed)
        else:
            await ctx.send("🤔 ไม่สามารถดึงข้อมูลเพลงที่กำลังเล่นได้")

    @play.before_invoke
    @skip.before_invoke
    @stop.before_invoke
    @nowplaying.before_invoke
    async def ensure_voice_connection(self, ctx):
        """
        Decorator ที่ทำงานก่อนคำสั่ง play, skip, stop, nowplaying
        เพื่อให้แน่ใจว่าบอทเชื่อมต่อกับช่องเสียง (ถ้าจำเป็นสำหรับคำสั่งนั้นๆ)
        หรือผู้ใช้เชื่อมต่อกับช่องเสียง
        """
        if ctx.command.name != 'play': # play command handles its own voice channel joining logic
            if not ctx.guild.voice_client:
                await ctx.send("⚠️ บอทไม่ได้เชื่อมต่อกับช่องเสียงใดๆ เลยนะ ลองใช้ `#play` เพื่อให้บอทเข้ามา") # แก้ไขตัวอย่าง prefix
                raise commands.CommandError("Bot is not connected to a voice channel.")
            
            if not ctx.author.voice or ctx.author.voice.channel != ctx.guild.voice_client.channel:
                await ctx.send("⚠️ คุณต้องอยู่ในช่องเสียงเดียวกับบอทเพื่อใช้คำสั่งนี้")
                raise commands.CommandError("User is not in the same voice channel as the bot.")


@bot.event
async def on_ready():
    """
    ฟังก์ชันที่จะทำงานเมื่อบอทพร้อมใช้งาน
    """
    print(f'🤖 {bot.user.name} พร้อมให้บริการแล้วจ้า!')
    print(f'🆔 ID ของบอท: {bot.user.id}')
    print('------')
    # เพิ่ม dictionary สำหรับเก็บเพลงที่กำลังเล่น
    bot.current_song = {} # {guild_id: song_info}
    # เพิ่ม cog เข้าไปในบอท
    await bot.add_cog(MusicCog(bot))


# ตรวจสอบว่า token ถูกใส่หรือยัง
if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    print("🚨 โปรดใส่ BOT_TOKEN ของคุณในโค้ดก่อนรันบอท!")
else:
    try:
        bot.run(BOT_TOKEN)
    except discord.errors.LoginFailure:
        print("🚨 ไม่สามารถล็อกอินได้ โปรดตรวจสอบ BOT_TOKEN อีกครั้ง")
    except Exception as e:
        print(f"🚨 เกิดข้อผิดพลาดในการรันบอท: {e}")

