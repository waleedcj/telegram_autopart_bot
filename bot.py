import os
from dotenv import load_dotenv
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import json
import logging
from logging.handlers import RotatingFileHandler

# Load environment variables
load_dotenv()

# Get environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBAPP_URL = os.getenv('WEBAPP_URL')

# States for conversation handler
SELECTING_CAR, SELECTING_PART, CONFIRMING_REQUEST, SELECTING_RESPONSE, ENTERING_PRICE = range(5)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('bot.log', maxBytes=1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AutoPartsBot:
    def __init__(self):
        # Load seller data from JSON
        with open('sellers.json', 'r') as f:
            self.sellers = json.load(f)
        
        # Store active requests
        self.active_requests = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message with Web App keyboard button when /start is issued."""
        # Create a keyboard with a WebApp button
        keyboard = [[
            KeyboardButton(
                text="🔍 Open Parts Finder",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ]]
        reply_markup = ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True  # Makes the keyboard smaller
        )
        
        await update.message.reply_text(
            "Welcome to UAE Auto Parts Bot! 🚗\n"
            "Tap the button below to search for parts:",
            reply_markup=reply_markup
        )

    async def search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the search process."""
        keyboard = [
            [InlineKeyboardButton("Toyota", callback_data="brand_toyota")],
            [InlineKeyboardButton("Honda", callback_data="brand_honda")],
            [InlineKeyboardButton("Nissan", callback_data="brand_nissan")],
            [InlineKeyboardButton("BMW", callback_data="brand_bmw")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Please select your car brand:", reply_markup=reply_markup)
        return SELECTING_CAR

    async def car_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle car brand selection."""
        query = update.callback_query
        await query.answer()
        
        brand = query.data.split('_')[1]
        context.user_data['brand'] = brand
        
        await query.edit_message_text(
            f"You selected {brand}. Now, please describe the part you need:"
        )
        return SELECTING_PART

    async def part_requested(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle part description."""
        part_description = update.message.text
        context.user_data['part'] = part_description
        brand = context.user_data['brand']
        
        # Create confirmation message
        confirmation_text = (
            f"Please confirm your request:\n"
            f"Brand: {brand}\n"
            f"Part needed: {part_description}"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("Confirm", callback_data="confirm"),
                InlineKeyboardButton("Cancel", callback_data="cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(confirmation_text, reply_markup=reply_markup)
        return CONFIRMING_REQUEST

    async def handle_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle request confirmation."""
        query = update.callback_query
        await query.answer()
        
        if query.data == "confirm":
            # Store the request
            request_data = {
                'user_id': update.effective_user.id,
                'brand': context.user_data['brand'],
                'part': context.user_data['part'],
                'status': 'pending'
            }
            
            # Notify relevant sellers (you'll need to implement this)
            await self.notify_sellers(request_data)
            
            await query.edit_message_text(
                "Your request has been sent to relevant sellers. "
                "They will contact you through this bot if they have the part available."
            )
        else:
            await query.edit_message_text("Request cancelled. Use /search to start a new search.")
        
        return ConversationHandler.END

    async def notify_sellers(self, request_data):
        """Notify relevant sellers about the new request."""
        brand = request_data['brand']
        
        relevant_sellers = [
            s for s in self.sellers 
            if isinstance(s, dict) and 'brands' in s and 'contact' in s and brand.lower() in [b.lower() for b in s['brands']]
        ]
        
        logging.info(f"Found {len(relevant_sellers)} relevant sellers for brand {brand}")
        
        for seller in relevant_sellers:
            notification_text = (
                f"New part request!\n"
                f"Brand: {request_data['brand']}\n"
                f"Part needed: {request_data['part']}\n"
                f"Use /respond_{request_data['user_id']} to respond to this request"
            )
            if 'telegram_id' in seller['contact']:
                try:
                    logging.info(f"Attempting to send message to seller {seller['id']} with telegram_id {seller['contact']['telegram_id']}")
                    await self.bot.send_message(
                        chat_id=seller['contact']['telegram_id'],
                        text=notification_text
                    )
                    logging.info(f"Successfully sent message to seller {seller['id']}")
                except Exception as e:
                    logging.error(f"Failed to send notification to seller {seller['id']}: {str(e)}")

    async def handle_seller_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle when a seller responds to a request."""
        command = update.message.text.split('_')
        if len(command) != 2:
            await update.message.reply_text("Invalid response command.")
            return ConversationHandler.END
        
        customer_id = command[1]
        context.user_data['customer_id'] = customer_id
        
        keyboard = [
            [
                InlineKeyboardButton("Available", callback_data="available"),
                InlineKeyboardButton("Not Available", callback_data="not_available")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Do you have this part available?",
            reply_markup=reply_markup
        )
        return SELECTING_RESPONSE

    async def handle_availability_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the seller's availability response."""
        query = update.callback_query
        await query.answer()
        
        if query.data == "available":
            await query.edit_message_text("Please enter the price for this part (in AED):")
            return ENTERING_PRICE
        else:
            # Notify customer that part is not available
            customer_id = context.user_data['customer_id']
            try:
                await context.bot.send_message(
                    chat_id=customer_id,
                    text=f"A seller has responded: The requested part is not available."
                )
                await query.edit_message_text("Response sent to customer.")
            except Exception as e:
                await query.edit_message_text("Error sending response to customer.")
            return ConversationHandler.END

    async def handle_price_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the price entry from seller."""
        try:
            price = float(update.message.text)
            customer_id = context.user_data['customer_id']
            seller_name = update.effective_user.username or "A seller"
            
            # Send price quote to customer
            customer_message = (
                f"💰 Price Quote Received!\n"
                f"From: {seller_name}\n"
                f"Price: {price} AED\n\n"
                f"You can contact the seller directly at @{update.effective_user.username}"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=customer_id,
                    text=customer_message
                )
                await update.message.reply_text("Price quote sent to customer successfully!")
            except Exception as e:
                await update.message.reply_text("Error sending price quote to customer.")
            
        except ValueError:
            await update.message.reply_text(
                "Please enter a valid number for the price."
            )
            return ENTERING_PRICE
            
        return ConversationHandler.END

    async def handle_webapp_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle data received from the web app."""
        try:
            logger.info("🟢 Starting handle_webapp_data")
            
            # Parse the received data
            data = json.loads(update.effective_message.web_app_data.data)
            logger.info(f"📥 Received web app data: {data}")
            
            # Add user info to the request data
            data['user_id'] = update.effective_user.id
            data['username'] = update.effective_user.username
            logger.info(f"👤 Added user info: {data['username']} (ID: {data['user_id']})")
            
            # Store the request
            self.active_requests[str(update.effective_user.id)] = data
            logger.info(f"💾 Stored request in active_requests")
            
            # Load sellers
            try:
                with open('sellers.json', 'r') as f:
                    self.sellers = json.load(f)
                    logger.info(f"📚 Loaded sellers from file: {len(self.sellers)} sellers found")
            except Exception as e:
                logger.error(f"❌ Error loading sellers.json: {e}")
                raise
            
            # Notify sellers
            logger.info("🔔 Starting seller notification process")
            await self.notify_sellers(data, context)
            
            # Confirm to user
            await update.message.reply_text(
                "✅ Your request has been sent to relevant sellers. "
                "You will be notified when they respond."
            )
            logger.info("✅ Successfully completed handle_webapp_data")
            
        except Exception as e:
            logger.error(f"❌ Error in handle_webapp_data: {e}", exc_info=True)
            await update.message.reply_text(
                "❌ Sorry, there was an error processing your request. Please try again."
            )

    async def notify_sellers(self, request_data, context):
        """Notify relevant sellers about the new request."""
        logger.info(f"🔔 Starting notify_sellers for brand: {request_data.get('brand', 'unknown')}")
        
        brand = request_data.get('brand', '').lower()
        logger.info(f"🔍 Looking for sellers that handle brand: {brand}")
        
        # Debug log the sellers data
        logger.info(f"📋 Available sellers: {self.sellers}")
        
        relevant_sellers = [
            s for s in self.sellers 
            if isinstance(s, dict) and 'brands' in s and brand in [b.lower() for b in s['brands']]
        ]
        
        logger.info(f"✨ Found {len(relevant_sellers)} relevant sellers")
        
        for seller in relevant_sellers:
            logger.info(f"📤 Preparing to notify seller: {seller.get('name', 'Unknown')}")
            
            notification_text = (
                f"🚗 New Part Request!\n\n"
                f"Brand: {request_data['brand']}\n"
                f"Model: {request_data['model']}\n"
                f"Year: {request_data['year']}\n"
                f"Category: {request_data.get('category', 'N/A')}\n"
                f"Subcategory: {request_data.get('subcategory', 'N/A')}\n"
                f"Description: {request_data.get('description', 'N/A')}\n\n"
                f"Use /respond_{request_data['user_id']} to respond to this request"
            )
            
            if 'contact' in seller and 'telegram_id' in seller['contact']:
                try:
                    seller_id = seller['contact']['telegram_id']
                    logger.info(f"📨 Attempting to send message to seller {seller['id']} with telegram_id {seller_id}")
                    
                    await context.bot.send_message(
                        chat_id=seller_id,
                        text=notification_text
                    )
                    logger.info(f"✅ Successfully sent message to seller {seller['id']}")
                except Exception as e:
                    logger.error(f"❌ Failed to send notification to seller {seller['id']}: {str(e)}")
            else:
                logger.error(f"❌ Missing contact info for seller {seller.get('id', 'Unknown')}")

def main():
    """Start the bot."""
    # Create the Application and pass it your bot's token
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    bot = AutoPartsBot()
    bot.bot = application.bot  # This line fixes the missing bot attribute
    
    # Create conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('search', bot.search)],
        states={
            SELECTING_CAR: [CallbackQueryHandler(bot.car_selected)],
            SELECTING_PART: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.part_requested)],
            CONFIRMING_REQUEST: [CallbackQueryHandler(bot.handle_confirmation)]
        },
        fallbacks=[],
    )

    # Add new seller response conversation handler
    seller_response_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^/respond_\d+$'), bot.handle_seller_response)],
        states={
            SELECTING_RESPONSE: [CallbackQueryHandler(bot.handle_availability_response)],
            ENTERING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_price_entry)]
        },
        fallbacks=[],
    )

    # Add all handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(conv_handler)
    application.add_handler(seller_response_handler)

    application.add_handler(MessageHandler(
        filters.StatusUpdate.WEB_APP_DATA, 
        bot.handle_webapp_data
    ))

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main() 