@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        return jsonify({'error': 'Invalid signature'}), 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # Stripe object သို့မဟုတ် dict ပုံစံ မည်သို့ပင်ဖြစ်စေ လုံခြုံစွာ metadata ယူခြင်း
        metadata = getattr(session, 'get', None)
        if callable(metadata):
            metadata_dict = session.get('metadata', {})
        else:
            metadata_dict = getattr(session, 'metadata', {})

        # telegram_id ကို ထပ်မံစစ်ဆေးပြီး ရယူခြင်း
        if isinstance(metadata_dict, dict):
            telegram_id = metadata_dict.get('telegram_id')
        else:
            telegram_id = getattr(metadata_dict, 'telegram_id', None)

        if telegram_id:
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users 
                    SET subscription_status = 'active' 
                    WHERE telegram_id = ?
                ''', (telegram_id,))
                conn.commit()
                conn.close()
                print(f"Subscription activated for Telegram ID: {telegram_id}")
            except Exception as e:
                print(f"Database error updating subscription: {e}")

    return jsonify({'status': 'success'}), 200