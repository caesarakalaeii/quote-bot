# Discord Quote Bot

A Discord bot that allows users to submit quotes via DM, vote on them using buttons, and automatically stores approved quotes in a PostgreSQL database for later retrieval.

## Features

- 📤 **Quote Submission**: Users can submit quotes by sending a DM to the bot
- 🗳️ **Community Voting**: Quotes are posted with voting buttons (👍/👎) for community approval
- ⏰ **Automatic Processing**: After 7 days (configurable), quotes are automatically approved or rejected based on votes
- 📚 **Quote Storage**: Approved quotes are stored in a PostgreSQL database
- 🎲 **Random Retrieval**: Users can get random approved quotes using commands
- 📊 **Statistics**: View bot statistics and approved quote counts

## Setup

### Prerequisites

- Python 3.8+
- PostgreSQL database
- Discord bot token

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd quote-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your PostgreSQL database (create database and user)

4. Configure environment variables:
```bash
cp .env.template .env
# Edit .env with your configuration
```

5. Run the bot:
```bash
python bot.py
```

## Configuration

All configuration is done via environment variables. Copy `.env.template` to `.env` and fill in your values:

### Required Variables

- `DISCORD_TOKEN`: Your Discord bot token from the Discord Developer Portal
- `DB_PASSWORD`: Password for your PostgreSQL database

### Optional Variables

- `GUILD_ID`: Specific Discord server ID (if you want to limit to one server)
- `DB_HOST`: Database host (default: localhost)
- `DB_PORT`: Database port (default: 5432)
- `DB_NAME`: Database name (default: quotebot)
- `DB_USER`: Database user (default: postgres)
- `VOTE_DURATION_DAYS`: How long voting lasts (default: 7 days)
- `MIN_VOTES_THRESHOLD`: Minimum votes needed for approval (default: 3)

## Database Setup

The bot will automatically create the necessary tables when it starts. Make sure your PostgreSQL database exists and the user has appropriate permissions.

Required tables (created automatically):
- `quotes`: Stores all submitted quotes and voting data
- `votes`: Tracks individual user votes
- `approved_quotes`: Stores quotes that passed the voting process

## Usage

### For Users

1. **Submit a Quote**: Send a DM to the bot with your quote
2. **Vote on Quotes**: Click 👍 or 👎 buttons on quote posts
3. **Get Random Quote**: Use `!quote` command in any channel
4. **View Statistics**: Use `!stats` command
5. **Get Help**: Use `!help_quotes` command

### Quote Approval Process

1. User submits quote via DM
2. Bot posts quote in designated channel with voting buttons
3. Community votes for 7 days (configurable)
4. Quote is automatically approved if:
   - Net score is positive (upvotes > downvotes)
   - Minimum vote threshold is met
5. Approved quotes are stored permanently and available via `!quote` command

## Commands

- `!quote` - Get a random approved quote
- `!stats` - Show bot statistics
- `!help_quotes` - Show help information

## Bot Permissions

The bot needs the following Discord permissions:
- Send Messages
- Read Message History
- Use Slash Commands (optional)
- Add Reactions
- Embed Links
- Read Messages/View Channels

## Development

### Project Structure

```
quote-bot/
├── bot.py          # Main bot implementation
├── config.py       # Configuration management
├── database.py     # Database operations
├── requirements.txt # Python dependencies
├── .env.template   # Environment variable template
└── README.md       # This file
```

### Key Components

- **QuoteBot**: Main bot class handling Discord events
- **Database**: PostgreSQL connection and operations
- **QuoteVotingView**: Discord UI components for voting buttons
- **Config**: Environment variable management

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.