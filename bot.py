import re

class QuoteBot:
    # Existing methods...

    def handle_quote_mention_reply(self, message):
        """Handle replies that mention @quotebot to submit a quote."""
        if '@quotebot' not in message.content:
            return "This message is not mentioning me."

        original_message_id = message.reference.message_id  # Get the ID of the original message
        original_message = self.get_original_message(original_message_id)  # Fetch the original message
        
        if not original_message:
            return "Original message not found."

        if self.quote_exists(original_message.content):
            return "This quote already exists."

        # Post the quote for voting with proper attribution
        self.post_quote_for_voting(original_message.content, message.author)

    def get_original_message(self, message_id):
        """Fetch original message using the message ID."""
        # Implement fetching logic here...
        pass

    def quote_exists(self, quote):
        """Check if the given quote already exists."""
        # Implement duplicate checking logic here...
        pass

    def post_quote_for_voting(self, quote, author):
        """Post the quote for voting with proper attribution."""
        # Implement posting logic here...
        pass

    def help_command(self):
        """Display help for using the bot."""
        return """
        Help - Quote Bot
        1. To submit a quote, you can either:
           - Directly send a message mentioning @quotebot.
           - Reply to a message mentioning @quotebot to submit that message as a quote.
        2. Ensure your quote is unique to avoid duplicates.
        """