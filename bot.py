"""Discord Quote Bot - Main bot implementation."""
import discord
from discord.ext import commands, tasks
import logging
import asyncio
from datetime import datetime
from config import Config
from database import Database

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

class QuoteBot(commands.Bot):
    """Main Discord bot class for quote voting."""
    
    def __init__(self):
        super().__init__(
            command_prefix='!',
            intents=intents,
            description="A bot for voting on quotes and storing approved ones."
        )
        self.db = None
        
    async def setup_hook(self):
        """Set up the bot after login."""
        logger.info("Setting up bot...")
        try:
            self.db = Database()
            logger.info("Database connected successfully")
            
            # Start the background task for processing votes
            self.process_old_quotes.start()
            logger.info("Background tasks started")
            
        except Exception as e:
            logger.error(f"Setup failed: {e}")
            raise
    
    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info(f'{self.user} has logged in!')
        logger.info(f'Bot is in {len(self.guilds)} guilds')
    
    async def on_message(self, message):
        """Handle incoming messages."""
        # Ignore messages from the bot itself
        if message.author == self.user:
            return
        
        # Handle DMs (quote submissions)
        if isinstance(message.channel, discord.DMChannel):
            await self.handle_quote_submission(message)
        
        # Handle reply mentions (quote submissions via reply)
        if (message.reference and 
            message.reference.message_id and 
            self.user in message.mentions):
            await self.handle_quote_mention_reply(message)
        
        # Process commands
        await self.process_commands(message)
    
    async def handle_quote_mention_reply(self, message):
        """Handle replies that mention @quotebot to submit a quote."""
        try:
            # Fetch the original message being replied to
            try:
                original_message = await message.channel.fetch_message(message.reference.message_id)
            except discord.NotFound:
                await message.reply("❌ Original message not found!")
                return
            except discord.Forbidden:
                await message.reply("❌ I don't have permission to access the original message!")
                return
            
            # Validation: Don't quote bot messages
            if original_message.author.bot:
                await message.reply("❌ Can't quote bot messages!")
                return
            
            # Validation: Don't quote empty messages
            quote_content = original_message.content.strip()
            if not quote_content:
                await message.reply("❌ Can't quote empty messages!")
                return
            
            # Basic validation for quote length
            if len(quote_content) < 10:
                await message.reply("❌ Quote too short! Message must have at least 10 characters.")
                return
            
            if len(quote_content) > 1000:
                await message.reply("❌ Quote too long! Message must be under 1000 characters.")
                return
            
            # Check for duplicates
            if self.db.quote_exists(quote_content):
                await message.reply("❌ This quote already exists!")
                return
            
            # Post quote for voting with proper attribution
            voting_message = await self.post_quote_for_voting(
                quote_content, 
                original_message.author, 
                submitted_by=message.author,
                original_message_url=original_message.jump_url
            )
            
            if voting_message:
                # Store quote in database
                quote_id = self.db.add_quote(
                    content=quote_content,
                    author_id=original_message.author.id,
                    author_name=str(original_message.author),
                    message_id=voting_message.id,
                    channel_id=voting_message.channel.id,
                    submitted_by_id=message.author.id,
                    submitted_by_name=str(message.author)
                )
                
                # Update the message to include the quote ID
                await self.update_voting_message_with_quote_id(voting_message, quote_id)
                
                # Confirm submission to user
                await message.reply("✅ Quote has been submitted for voting! The community will vote on it for one week.")
            else:
                await message.reply("❌ Failed to post quote for voting. Please try again.")
                
        except Exception as e:
            logger.error(f"Error handling quote mention reply: {e}")
            await message.reply("❌ Sorry, there was an error submitting the quote. Please try again.")

    async def handle_quote_submission(self, message):
        """Handle quote submissions via DM."""
        try:
            quote_content = message.content.strip()
            
            # Basic validation
            if len(quote_content) < 10:
                await message.reply("Quote too short! Please submit a quote with at least 10 characters.")
                return
            
            if len(quote_content) > 1000:
                await message.reply("Quote too long! Please keep it under 1000 characters.")
                return
            
            # Post quote for voting first to get message and channel IDs
            voting_message = await self.post_quote_for_voting(quote_content, message.author)
            
            if voting_message:
                # Now store quote in database with the actual message and channel IDs
                quote_id = self.db.add_quote(
                    content=quote_content,
                    author_id=message.author.id,
                    author_name=str(message.author),
                    message_id=voting_message.id,
                    channel_id=voting_message.channel.id,
                    submitted_by_id=message.author.id,
                    submitted_by_name=str(message.author)
                )
                
                # Update the message to include the quote ID
                await self.update_voting_message_with_quote_id(voting_message, quote_id)
                
                # Confirm submission to user
                await message.reply("✅ Your quote has been submitted for voting! The community will vote on it for one week.")
            else:
                await message.reply("❌ Failed to post quote for voting. Please try again.")
                
        except Exception as e:
            logger.error(f"Error handling quote submission: {e}")
            await message.reply("❌ Sorry, there was an error submitting your quote. Please try again.")
    
    async def post_quote_for_voting(self, quote_content, author, submitted_by=None, original_message_url=None):
        """Post a quote in the voting channel with voting buttons. Returns the message object."""
        try:
            # Find a suitable channel to post the quote
            guild = None
            channel = None
            
            # First, try to use the configured vote channel ID
            if Config.VOTE_CHANNEL_ID:
                channel = self.get_channel(int(Config.VOTE_CHANNEL_ID))
                if channel:
                    logger.info(f"Using configured vote channel: {channel.name}")
                else:
                    logger.warning(f"Configured vote channel ID {Config.VOTE_CHANNEL_ID} not found")
            
            # If no specific channel configured or channel not found, use fallback logic
            if not channel:
                if Config.GUILD_ID:
                    guild = self.get_guild(int(Config.GUILD_ID))
                    if guild:
                        channel = discord.utils.find(lambda c: c.name == 'quotes' or c.name == 'quote-voting', guild.text_channels)
                        if not channel:
                            channel = guild.text_channels[0]  # Fallback to first channel
                
                if not channel:
                    # Fallback: use the first guild's first channel
                    if self.guilds:
                        guild = self.guilds[0]
                        channel = guild.text_channels[0]
            
            if not channel:
                logger.error("No suitable channel found to post quote")
                return None
            
            # Create embed for the quote
            embed = discord.Embed(
                title="📝 New Quote Submission",
                description=f'"{quote_content}"',
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            # Attribution: Show both quote author and submitter if different
            if submitted_by and submitted_by != author:
                embed.add_field(name="Quote Author", value=author.mention, inline=True)
                embed.add_field(name="Submitted by", value=submitted_by.mention, inline=True)
            else:
                embed.add_field(name="Submitted by", value=author.mention, inline=True)
            
            embed.add_field(name="Voting ends", value=f"<t:{int((datetime.now().timestamp() + 7*24*3600))}:R>", inline=True)
            
            # Add link to original message if provided
            if original_message_url:
                embed.add_field(name="Original Message", value=f"[Jump to Message]({original_message_url})", inline=False)
            
            embed.set_footer(text="Quote ID will be assigned after database entry")
            
            # Create voting view with buttons (quote_id will be set later)
            view = QuoteVotingView(None, self.db)
            
            # Send the message
            message = await channel.send(embed=embed, view=view)
            
            logger.info(f"Quote posted for voting in {channel.name}")
            return message
            
        except Exception as e:
            logger.error(f"Error posting quote for voting: {e}")
            return None
    
    async def update_voting_message_with_quote_id(self, message, quote_id):
        """Update the voting message with the actual quote ID."""
        try:
            # Update the embed footer with the real quote ID
            embed = message.embeds[0]
            embed.set_footer(text=f"Quote ID: {quote_id}")
            
            # Update the view with the quote ID
            view = QuoteVotingView(quote_id, self.db)
            
            await message.edit(embed=embed, view=view)
            logger.info(f"Updated voting message with quote ID {quote_id}")
            
        except Exception as e:
            logger.error(f"Error updating voting message with quote ID: {e}")
    
    @tasks.loop(hours=6)  # Check every 6 hours
    async def process_old_quotes(self):
        """Process quotes that have completed their voting period."""
        try:
            quotes_to_process = self.db.get_quotes_ready_for_processing()
            
            for quote in quotes_to_process:
                net_score = quote['upvotes'] - quote['downvotes']
                total_votes = quote['upvotes'] + quote['downvotes']
                
                # Determine if quote should be approved
                # Quote is approved if: net positive score AND meets minimum vote threshold
                should_approve = (net_score > 0 and total_votes >= Config.MIN_VOTES_THRESHOLD)
                
                # Process the quote
                self.db.process_quote(quote['id'], approved=should_approve)
                
                # Update the original message to show results
                await self.update_quote_voting_message(quote, should_approve)
                
                logger.info(f"Processed quote {quote['id']}: {'approved' if should_approve else 'rejected'}")
            
            if quotes_to_process:
                logger.info(f"Processed {len(quotes_to_process)} quotes")
        
        except Exception as e:
            logger.error(f"Error processing old quotes: {e}")
    
    async def update_quote_voting_message(self, quote, approved):
        """Update the voting message to show final results."""
        try:
            if not quote['message_id'] or not quote['channel_id']:
                return
            
            channel = self.get_channel(int(quote['channel_id']))
            if not channel:
                return
            
            try:
                message = await channel.fetch_message(int(quote['message_id']))
            except discord.NotFound:
                logger.warning(f"Original message for quote {quote['id']} not found")
                return
            
            # Update embed with results
            embed = discord.Embed(
                title="📝 Quote Voting Results",
                description=f'"{quote["content"]}"',
                color=discord.Color.green() if approved else discord.Color.red(),
                timestamp=datetime.now()
            )
            embed.add_field(name="Submitted by", value=quote['author_name'], inline=True)
            embed.add_field(name="Final Score", value=f"👍 {quote['upvotes']} | 👎 {quote['downvotes']}", inline=True)
            embed.add_field(name="Result", value="✅ Approved!" if approved else "❌ Not approved", inline=True)
            embed.set_footer(text=f"Quote ID: {quote['id']} | Voting completed")
            
            # Remove the voting buttons by creating a new view with disabled buttons
            view = QuoteVotingView(quote['id'], self.db, disabled=True)
            view.update_vote_counts(quote['upvotes'], quote['downvotes'])
            
            await message.edit(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error updating voting message for quote {quote['id']}: {e}")
    
    async def close(self):
        """Clean up when bot is shutting down."""
        if self.db:
            self.db.close()
        await super().close()

class QuoteVotingView(discord.ui.View):
    """View for quote voting buttons."""
    
    def __init__(self, quote_id, db, disabled=False):
        super().__init__(timeout=None)  # Persistent view
        self.quote_id = quote_id
        self.db = db
        
        if disabled:
            self.upvote_button.disabled = True
            self.downvote_button.disabled = True
    
    def update_vote_counts(self, upvotes, downvotes):
        """Update button labels with vote counts."""
        self.upvote_button.label = f"👍 {upvotes}"
        self.downvote_button.label = f"👎 {downvotes}"
    
    @discord.ui.button(label="👍 0", style=discord.ButtonStyle.green, custom_id="upvote")
    async def upvote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle upvote button press."""
        await self.handle_vote(interaction, "upvote")
    
    @discord.ui.button(label="👎 0", style=discord.ButtonStyle.red, custom_id="downvote")
    async def downvote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle downvote button press."""
        await self.handle_vote(interaction, "downvote")
    
    async def handle_vote(self, interaction: discord.Interaction, vote_type):
        """Handle voting logic."""
        try:
            if self.quote_id is None:
                await interaction.response.send_message("❌ Quote not ready for voting yet!", ephemeral=True)
                return
            
            # Add vote to database
            self.db.add_vote(self.quote_id, interaction.user.id, str(interaction.user), vote_type)
            
            # Get updated vote counts
            vote_counts = self.db.get_vote_counts(self.quote_id)
            
            # Update button labels
            self.update_vote_counts(vote_counts['upvotes'], vote_counts['downvotes'])
            
            # Respond to interaction
            vote_emoji = "👍" if vote_type == "upvote" else "👎"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"{vote_emoji} Vote recorded!", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error handling vote: {e}")
            await interaction.response.send_message("❌ Error recording vote!", ephemeral=True)

# Bot commands
bot = QuoteBot()

@bot.command(name='quote')
async def random_quote(ctx):
    """Get a random approved quote."""
    try:
        quote = bot.db.get_random_approved_quote()
        
        if not quote:
            await ctx.send("📝 No approved quotes available yet! Submit some quotes via DM to get started.")
            return
        
        embed = discord.Embed(
            title="📝 Random Quote",
            description=f'"{quote["content"]}"',
            color=discord.Color.gold()
        )
        embed.add_field(name="Author", value=quote['author_name'], inline=True)
        embed.add_field(name="Approved", value=f"<t:{int(quote['approved_at'].timestamp())}:R>", inline=True)
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error getting random quote: {e}")
        await ctx.send("❌ Error retrieving quote!")

@bot.command(name='stats')
async def quote_stats(ctx):
    """Show quote bot statistics."""
    try:
        approved_count = bot.db.get_approved_quotes_count()
        
        embed = discord.Embed(
            title="📊 Quote Bot Statistics",
            color=discord.Color.blue()
        )
        embed.add_field(name="Approved Quotes", value=str(approved_count), inline=True)
        embed.add_field(name="Vote Duration", value=f"{Config.VOTE_DURATION_DAYS} days", inline=True)
        embed.add_field(name="Min Vote Threshold", value=str(Config.MIN_VOTES_THRESHOLD), inline=True)
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        await ctx.send("❌ Error retrieving statistics!")

@bot.command(name='help_quotes')
async def help_quotes(ctx):
    """Show help information for the quote bot."""
    embed = discord.Embed(
        title="📝 Quote Bot Help",
        description="A bot for submitting, voting on, and storing community quotes!",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="📤 Submitting Quotes",
        value="**Method 1:** Send me a DM with your quote!\n"
              "**Method 2:** Reply to any message and mention me (@quotebot) to submit that message as a quote!\n"
              "Both methods will post the quote for community voting.",
        inline=False
    )
    
    embed.add_field(
        name="🗳️ Voting",
        value="Click 👍 or 👎 on quote posts to vote. Quotes need positive net votes to be approved.",
        inline=False
    )
    
    embed.add_field(
        name="📚 Commands",
        value="`!quote` - Get a random approved quote\n`!stats` - Show bot statistics\n`!help_quotes` - Show this help",
        inline=False
    )
    
    embed.add_field(
        name="⏰ Voting Period",
        value=f"Quotes are voted on for {Config.VOTE_DURATION_DAYS} days, then automatically processed.",
        inline=False
    )
    
    embed.add_field(
        name="❓ Quote Requirements",
        value="• 10-1000 characters\n• No bot messages\n• No duplicates\n• Must have actual content",
        inline=False
    )
    
    await ctx.send(embed=embed)

async def main():
    """Main function to start the bot."""
    try:
        # Validate configuration
        Config.validate()
        
        # Start the bot
        logger.info("Starting Quote Bot...")
        await bot.start(Config.DISCORD_TOKEN)
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise
    finally:
        await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise