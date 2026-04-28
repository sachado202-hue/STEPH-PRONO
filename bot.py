import logging
import asyncio
import aiohttp
import sqlite3
import os
from datetime import datetime, date
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ============================================================
#  CONFIG
# ============================================================
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "7969169742:AAEp9YoO4IdnTZ4grCVQbkx1m9RWvKoDzQw")
FREE_CHANNEL   = "@stephpronofree"
VIP_CHANNEL_ID = -1003762469696
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "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")
SPORT_API_KEY  = os.environ.get("SPORT_API_KEY", "2be493dfb8mshdd67a4a2612c42bp18ba80jsn324f8427bfc0")
ADMIN_IDS      = [6752802391]
PROMO_CODE     = "STEPH2024"
GROQ_MODEL     = "llama-3.3-70b-versatile"
GROQ_URL       = "https://api.groq.com/openai/v1/chat/completions"

# ============================================================
#  LOGGING
# ============================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================
#  DATABASE
# ============================================================
def init_db():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id    INTEGER PRIMARY KEY,
        username   TEXT,
        first_name TEXT,
        is_vip     INTEGER DEFAULT 0,
        joined_at  TEXT
    )""")
    conn.commit()
    conn.close()

def save_user(user_id, username, first_name):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("""INSERT OR IGNORE INTO users (user_id,username,first_name,joined_at)
                 VALUES (?,?,?,?)""",
              (user_id, username or "", first_name or "", datetime.now().isoformat()))
    conn.commit()
    conn.close()

def set_vip(user_id, value=1):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET is_vip=? WHERE user_id=?", (value, user_id))
    conn.commit()
    conn.close()

def is_vip(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT is_vip FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row and row[0] == 1

def count_users():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE is_vip=1")
    vip = c.fetchone()[0]
    conn.close()
    return total, vip

# ============================================================
#  REPLY KEYBOARD (beau clavier en bas)
# ============================================================
def main_keyboard():
    """Le beau clavier avec 4 boutons carrés en bas"""
    keyboard = [
        [
            KeyboardButton("⚽ Tips Gratuits"),
            KeyboardButton("💎 Accès VIP"),
        ],
        [
            KeyboardButton("📊 Nos Résultats"),
            KeyboardButton("ℹ️ À Propos"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Choisis une option... 👇"
    )

def admin_keyboard():
    """Clavier admin avec commandes supplémentaires"""
    keyboard = [
        [
            KeyboardButton("⚽ Tips Gratuits"),
            KeyboardButton("💎 Accès VIP"),
        ],
        [
            KeyboardButton("📊 Nos Résultats"),
            KeyboardButton("ℹ️ À Propos"),
        ],
        [
            KeyboardButton("📤 Publier FREE"),
            KeyboardButton("💎 Publier VIP"),
        ],
        [
            KeyboardButton("👥 Statistiques"),
            KeyboardButton("🔧 Test IA"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Panel Admin 👑"
    )

def vip_inline():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ J'ai créé mon compte 1xBet", callback_data="check_promo")],
        [InlineKeyboardButton("⬅️ Retour", callback_data="back_home")],
    ])

def tips_inline():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 ACCÈS VIP GRATUIT 🎁", callback_data="become_vip")],
        [InlineKeyboardButton("🔄 Actualiser", callback_data="refresh_tips")],
    ])

def back_inline():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Retour", callback_data="back_home")]
    ])

# ============================================================
#  SPORT API — vrais matchs du jour
# ============================================================
async def get_todays_matches():
    today = date.today().strftime("%Y-%m-%d")
    headers = {
        "X-RapidAPI-Key": SPORT_API_KEY,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
    }
    matches = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api-football-v1.p.rapidapi.com/v3/fixtures",
                headers=headers,
                params={"date": today, "timezone": "Africa/Lome"},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                data = await resp.json()
                logger.info(f"API Football status: {resp.status}")
                if "response" in data and data["response"]:
                    for f in data["response"]:
                        status = f.get("fixture", {}).get("status", {}).get("short", "")
                        if status not in ["FT", "AET", "PEN", "CANC", "ABD"]:
                            matches.append({
                                "home":   f["teams"]["home"]["name"],
                                "away":   f["teams"]["away"]["name"],
                                "league": f["league"]["name"],
                                "time":   f["fixture"]["date"][11:16] + " UTC",
                            })
                    logger.info(f"✅ {len(matches)} matchs récupérés via API Football")
                else:
                    logger.warning(f"⚠️ Réponse API Football vide: {data}")
    except Exception as e:
        logger.error(f"❌ API Football erreur: {e}")
    if not matches:
        logger.warning("⚠️ Aucun match récupéré — l'IA va générer des matchs plausibles")
    return matches[:10]

# ============================================================
#  GROQ AI
# ============================================================
async def call_groq(prompt: str) -> str | None:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Tu es STEPH PRONO, l'expert analyste sportif numéro 1 en Afrique. "
                    "Tu génères des prédictions sportives ultra-détaillées et professionnelles en français. "
                    "Tes prédictions sont basées sur les statistiques, la forme des équipes, "
                    "les confrontations directes et les données récentes. "
                    "Utilise des emojis pour rendre tes analyses visuellement attractives et professionnelles."
                )
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 2000,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GROQ_URL, headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=40)
            ) as resp:
                data = await resp.json()
                if "error" in data:
                    logger.error(f"❌ Groq: {data['error']}")
                    return None
                text = data["choices"][0]["message"]["content"]
                logger.info("✅ Groq réponse OK")
                return text
    except Exception as e:
        logger.error(f"❌ Groq: {e}")
        return None

async def generate_predictions(matches, vip=False):
    today_str = date.today().strftime("%d/%m/%Y")

    if not matches:
        niveau = "5 tips VIP ultra-exclusifs" if vip else "3 tips gratuits solides"
        prompt = f"""Génère {niveau} de prédictions football pour aujourd'hui {today_str}.
Utilise des matchs réels plausibles des grands championnats européens d'aujourd'hui.
{"Inclus pour chaque tip : prédiction principale + tip bonus (BTTS/mi-temps) + analyse experte." if vip else "Choisis les 3 meilleurs matchs du moment."}

Format EXACT pour chaque tip :
━━━━━━━━━━━━━━━━━━━━
⚽ *[Équipe A]* 🆚 *[Équipe B]*
🏆 *Ligue :* [nom de la ligue]
⏰ *Heure :* [heure du match]
━━━━━━━━━━━━━━━━━━━━
🎯 *Prédiction :* [prédiction]
{"🎁 *Tip Bonus :* [BTTS/mi-temps/corners]" if vip else ""}
📊 *Confiance :* [🔥🔥🔥 Très élevé / 🔥🔥 Élevé / 🔥 Moyen]
💰 *Cote recommandée :* [X.XX]
💡 *Analyse :* [analyse experte en 2-3 lignes]

Réponds uniquement en français avec ce format exact."""
    else:
        match_list = "\n".join([
            f"• {m['home']} vs {m['away']} — {m['league']} à {m['time']}"
            for m in matches
        ])
        niveau = "5 tips VIP ultra-détaillés avec marchés alternatifs" if vip else "3 meilleurs tips gratuits"
        prompt = f"""Analyse ces vrais matchs du {today_str} et génère {niveau} :

MATCHS D'AUJOURD'HUI :
{match_list}

{"Pour chaque tip VIP : prédiction principale + tip bonus (BTTS/mi-temps/corners) + analyse approfondie." if vip else "Sélectionne uniquement les 3 matchs avec le meilleur potentiel."}

Format EXACT :
━━━━━━━━━━━━━━━━━━━━
⚽ *[Équipe A]* 🆚 *[Équipe B]*
🏆 *Ligue :* [nom]
⏰ *Heure :* [heure]
━━━━━━━━━━━━━━━━━━━━
🎯 *Prédiction :* [prédiction]
{"🎁 *Tip Bonus :* [tip alternatif]" if vip else ""}
📊 *Confiance :* [🔥🔥🔥 / 🔥🔥 / 🔥]
💰 *Cote :* [X.XX]
💡 *Analyse :* [2-3 lignes expertes]

Réponds en français avec ce format exact."""

    return await call_groq(prompt)

# ============================================================
#  TEXTES
# ============================================================
def welcome_text(name):
    return f"""
╔═══════════════════════╗
║  ⚡ *STEPH PRONO* ⚡  ║
║  _Prédictions par IA_  ║
╚═══════════════════════╝

👋 Salut *{name}* !

Bienvenue sur le bot de prédictions sportives *N°1* propulsé par l'Intelligence Artificielle ! 🤖🌍

━━━━━━━━━━━━━━━━━━━━
🆓 *GRATUIT* → 3 tips/jour soigneusement sélectionnés
💎 *VIP* → 5 tips exclusifs + analyses + tips bonus
━━━━━━━━━━━━━━━━━━━━

👇 *Utilise le menu en bas pour naviguer :*
"""

ABOUT_TEXT = """
╔═══════════════════════╗
║   ℹ️ *À PROPOS*        ║
╚═══════════════════════╝

🤖 *STEPH PRONO* est alimenté par l'Intelligence Artificielle de dernière génération.

📊 *Notre IA analyse :*
• ✅ Forme récente des équipes
• ✅ Confrontations directes (H2H)
• ✅ Stats de la saison en cours
• ✅ Blessures & suspensions
• ✅ Données météo & terrain

⚽ *Sports couverts :*
🏆 Football • 🏀 Basketball • 🎾 Tennis

👥 *Notre communauté :*
• Des milliers d'abonnés satisfaits
• Actif tous les jours 7j/7
• Support réactif

⚠️ *Avertissement :* Pariez de façon responsable et dans vos limites. Le jeu doit rester un plaisir.

🌍 _Fait avec ❤️ pour l'Afrique_
"""

RESULTS_TEXT = """
╔═══════════════════════╗
║  📊 *NOS RÉSULTATS*   ║
╚═══════════════════════╝

📅 *Cette semaine :*
✅ Man City vs Liverpool → 1 ✓
✅ PSG vs Marseille → Over 2.5 ✓
✅ Real Madrid vs Barça → BTTS ✓
✅ Bayern vs Dortmund → 1 ✓
❌ Juventus vs Inter → X ✗

━━━━━━━━━━━━━━━━━━━━
📈 *Taux de réussite ce mois :* 73%
💰 *ROI moyen :* +27%
🏆 *Meilleur tip du mois :* 4.50 ✓
━━━━━━━━━━━━━━━━━━━━

💎 _Les résultats VIP sont encore meilleurs !_
Rejoins le VIP pour les tips premium 🔥
"""

def vip_text():
    return f"""
╔═══════════════════════╗
║   💎 *ACCÈS VIP*      ║
╚═══════════════════════╝

🎁 *L'accès VIP est 100% GRATUIT !*

━━━━━━━━━━━━━━━━━━━━
📋 *Étapes simples :*

*1️⃣* Va sur → https://1xbet.com
*2️⃣* Clique *"S'inscrire"*
*3️⃣* Entre le code : `{PROMO_CODE}`
*4️⃣* Valide ton inscription
*5️⃣* Reviens ici & clique ✅
*6️⃣* Envoie ton screenshot
━━━━━━━━━━━━━━━━━━━━

💎 *Avantages VIP exclusifs :*
✅ 5 tips/jour (au lieu de 3)
✅ Tips bonus BTTS & mi-temps
✅ Analyses ultra-détaillées
✅ Alertes avant chaque match
✅ Canal privé 24h/24
✅ Support prioritaire
━━━━━━━━━━━━━━━━━━━━
"""

# ============================================================
#  COMMANDES
# ============================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username, user.first_name)

    # Clavier différent pour admin
    kbd = admin_keyboard() if user.id in ADMIN_IDS else main_keyboard()

    await update.message.reply_text(
        welcome_text(user.first_name),
        parse_mode="Markdown",
        reply_markup=kbd
    )

# ============================================================
#  HANDLER BOUTONS DU CLAVIER (Reply Keyboard)
# ============================================================
async def keyboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    # ── TIPS GRATUITS ──────────────────────────────────────
    if text == "⚽ Tips Gratuits":
        msg = await update.message.reply_text(
            "⏳ *L'IA analyse les matchs du jour...*\n\n"
            "🔍 Récupération des données sportives\n"
            "📊 Calcul des probabilités\n"
            "🤖 Génération des prédictions\n\n"
            "_Patiente environ 30 secondes_ ⌛",
            parse_mode="Markdown"
        )
        matches = await get_todays_matches()
        predictions = await generate_predictions(matches, vip=False)
        today = datetime.now().strftime("%d/%m/%Y")

        if not predictions:
            await msg.edit_text(
                "⚠️ *Service momentanément indisponible.*\nRéessaie dans quelques minutes. 🔄",
                parse_mode="Markdown"
            )
            return

        header = (
            f"╔═══════════════════════╗\n"
            f"║  ⚡ *TIPS GRATUITS*  ⚡ ║\n"
            f"║    📅 *{today}*    ║\n"
            f"╚═══════════════════════╝\n\n"
        )
        footer = (
            f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 *Veux-tu 5 tips VIP exclusifs ?*\n"
            f"👇 Rejoins le VIP *GRATUITEMENT* !"
        )
        try:
            await msg.edit_text(
                header + predictions + footer,
                parse_mode="Markdown",
                reply_markup=tips_inline()
            )
        except Exception:
            await update.message.reply_text(
                header + predictions + footer,
                parse_mode="Markdown",
                reply_markup=tips_inline()
            )

    # ── ACCÈS VIP ──────────────────────────────────────────
    elif text == "💎 Accès VIP":
        await update.message.reply_text(
            vip_text(),
            parse_mode="Markdown",
            reply_markup=vip_inline(),
            disable_web_page_preview=True
        )

    # ── RÉSULTATS ──────────────────────────────────────────
    elif text == "📊 Nos Résultats":
        await update.message.reply_text(
            RESULTS_TEXT,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Accès VIP pour + de wins", callback_data="become_vip")]
            ])
        )

    # ── À PROPOS ───────────────────────────────────────────
    elif text == "ℹ️ À Propos":
        await update.message.reply_text(ABOUT_TEXT, parse_mode="Markdown")

    # ── ADMIN : PUBLIER FREE ───────────────────────────────
    elif text == "📤 Publier FREE" and user.id in ADMIN_IDS:
        msg = await update.message.reply_text("⏳ Génération tips FREE...")
        matches = await get_todays_matches()
        predictions = await generate_predictions(matches, vip=False)
        if not predictions:
            await msg.edit_text("❌ Erreur génération.")
            return
        today = datetime.now().strftime("%d/%m/%Y")
        canal_msg = (
            f"╔═══════════════════════╗\n"
            f"║  🌅 *TIPS DU JOUR*  🌅 ║\n"
            f"║    📅 *{today}*    ║\n"
            f"╚═══════════════════════╝\n\n"
            f"{predictions}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 *5 tips VIP disponibles !*\n"
            f"👉 Tape /start dans le bot"
        )
        try:
            await context.bot.send_message(FREE_CHANNEL, canal_msg, parse_mode="Markdown")
            await msg.edit_text("✅ Tips publiés sur le canal FREE ! 🎉")
        except Exception as e:
            await msg.edit_text(f"❌ Erreur : {e}")

    # ── ADMIN : PUBLIER VIP ────────────────────────────────
    elif text == "💎 Publier VIP" and user.id in ADMIN_IDS:
        msg = await update.message.reply_text("⏳ Génération tips VIP...")
        matches = await get_todays_matches()
        predictions = await generate_predictions(matches, vip=True)
        if not predictions:
            await msg.edit_text("❌ Erreur génération.")
            return
        today = datetime.now().strftime("%d/%m/%Y")
        canal_msg = (
            f"╔═══════════════════════╗\n"
            f"║ 💎 *TIPS VIP EXCLUSIFS* ║\n"
            f"║    📅 *{today}*    ║\n"
            f"╚═══════════════════════╝\n\n"
            f"{predictions}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ _Pariez de façon responsable._\n"
            f"🏆 *STEPH PRONO — L'IA au service de vos gains* ⚡"
        )
        try:
            await context.bot.send_message(VIP_CHANNEL_ID, canal_msg, parse_mode="Markdown")
            await msg.edit_text("✅ Tips VIP publiés ! 💎")
        except Exception as e:
            await msg.edit_text(f"❌ Erreur : {e}")

    # ── ADMIN : STATS ──────────────────────────────────────
    elif text == "👥 Statistiques" and user.id in ADMIN_IDS:
        total, vip = count_users()
        await update.message.reply_text(
            f"╔═══════════════════════╗\n"
            f"║  📊 *STATS BOT*  👑   ║\n"
            f"╚═══════════════════════╝\n\n"
            f"👥 *Total :* {total} utilisateurs\n"
            f"💎 *VIP :* {vip}\n"
            f"🆓 *Gratuit :* {total - vip}\n\n"
            f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            parse_mode="Markdown"
        )

    # ── ADMIN : TEST IA ────────────────────────────────────
    elif text == "🔧 Test IA" and user.id in ADMIN_IDS:
        msg = await update.message.reply_text("🔍 Test Groq en cours...")
        result = await call_groq("Dis 'IA opérationnelle ✅' en français.")
        if result:
            await msg.edit_text(
                f"✅ *Groq fonctionne parfaitement !*\n\n_{result[:200]}_",
                parse_mode="Markdown"
            )
        else:
            await msg.edit_text("❌ Groq ne répond pas.")

# ============================================================
#  INLINE BUTTONS HANDLER
# ============================================================
async def btn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "become_vip":
        await query.edit_message_text(
            vip_text(),
            parse_mode="Markdown",
            reply_markup=vip_inline(),
            disable_web_page_preview=True
        )

    elif query.data == "check_promo":
        context.user_data["waiting_screenshot"] = True
        await query.edit_message_text(
            "📸 *Envoie ton screenshot maintenant !*\n\n"
            "Montre-nous :\n"
            "✅ Ton compte 1xBet créé\n"
            "✅ Le code promo utilisé\n\n"
            "_Accès VIP activé dans les plus brefs délais_ ⚡",
            parse_mode="Markdown"
        )

    elif query.data == "refresh_tips":
        await query.edit_message_text(
            "⏳ *Actualisation des tips...*\n\n🤖 L'IA re-analyse les matchs...",
            parse_mode="Markdown"
        )
        matches = await get_todays_matches()
        predictions = await generate_predictions(matches, vip=False)
        today = datetime.now().strftime("%d/%m/%Y")
        if predictions:
            header = (
                f"╔═══════════════════════╗\n"
                f"║  ⚡ *TIPS GRATUITS*  ⚡ ║\n"
                f"║    📅 *{today}*    ║\n"
                f"╚═══════════════════════╝\n\n"
            )
            footer = (
                f"\n━━━━━━━━━━━━━━━━━━━━\n"
                f"💎 *Veux-tu 5 tips VIP exclusifs ?*\n"
                f"👇 Rejoins le VIP *GRATUITEMENT* !"
            )
            try:
                await query.edit_message_text(
                    header + predictions + footer,
                    parse_mode="Markdown",
                    reply_markup=tips_inline()
                )
            except Exception:
                pass

    elif query.data == "back_home":
        user = query.from_user
        await query.edit_message_text(
            welcome_text(user.first_name),
            parse_mode="Markdown"
        )

# ============================================================
#  MESSAGE HANDLER (screenshots VIP)
# ============================================================
async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ""

    # Screenshot VIP en attente
    if context.user_data.get("waiting_screenshot"):
        if update.message.photo:
            context.user_data["waiting_screenshot"] = False
            for admin_id in ADMIN_IDS:
                try:
                    caption = (
                        f"🆕 *NOUVELLE DEMANDE VIP* 💎\n\n"
                        f"👤 *Nom :* {user.first_name}\n"
                        f"🔗 *Username :* @{user.username or 'N/A'}\n"
                        f"🆔 *ID :* `{user.id}`\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"✅ `/approve {user.id}`\n"
                        f"❌ `/reject {user.id}`"
                    )
                    await context.bot.send_photo(
                        chat_id=admin_id,
                        photo=update.message.photo[-1].file_id,
                        caption=caption,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Erreur notif admin: {e}")

            await update.message.reply_text(
                "✅ *Screenshot reçu avec succès !*\n\n"
                "⏳ Notre équipe vérifie ton compte.\n"
                "Ton accès VIP sera activé très rapidement ! 💎\n\n"
                "_Merci pour ta confiance !_ 🙏",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "📸 J'attends une *image* (capture d'écran).\n\n"
                "_Appuie sur 📎 et sélectionne une photo._",
                parse_mode="Markdown"
            )
        return

    # Commandes admin
    if user.id not in ADMIN_IDS:
        return

    if text.startswith("/approve"):
        parts = text.split()
        if len(parts) == 2:
            uid = int(parts[1])
            set_vip(uid)
            try:
                invite = await context.bot.create_chat_invite_link(
                    VIP_CHANNEL_ID, member_limit=1)
                await context.bot.send_message(
                    uid,
                    f"🎉 *FÉLICITATIONS ! Tu es maintenant VIP* 💎\n\n"
                    f"👉 *Rejoins le canal VIP :*\n{invite.invite_link}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💎 *Bienvenue dans l'élite STEPH PRONO !* 🏆\n"
                    f"_5 tips exclusifs chaque matin à 9h_ ⚡",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Erreur lien VIP: {e}")
            await update.message.reply_text(
                f"✅ User `{uid}` approuvé VIP ! 💎",
                parse_mode="Markdown"
            )

    elif text.startswith("/reject"):
        parts = text.split()
        if len(parts) == 2:
            uid = int(parts[1])
            await context.bot.send_message(
                uid,
                f"❌ *Demande VIP refusée*\n\n"
                f"Le code promo n'a pas été détecté.\n\n"
                f"💡 *Réessaie :*\n"
                f"1️⃣ Crée un NOUVEAU compte 1xBet\n"
                f"2️⃣ Code promo : `{PROMO_CODE}`\n"
                f"3️⃣ Tape /start",
                parse_mode="Markdown"
            )
            await update.message.reply_text(
                f"❌ User `{uid}` rejeté.",
                parse_mode="Markdown"
            )

    elif text.startswith("/setpromo"):
        parts = text.split()
        if len(parts) == 2:
            PROMO_CODE = parts[1].upper()
            await update.message.reply_text(
                f"✅ Code promo mis à jour : `{PROMO_CODE}`",
                parse_mode="Markdown"
            )

# ============================================================
#  AUTO PUBLISH 9h00
# ============================================================
async def auto_publish(context: ContextTypes.DEFAULT_TYPE):
    logger.info("🕘 Auto-publication...")
    matches = await get_todays_matches()
    today = datetime.now().strftime("%d/%m/%Y")

    # FREE
    pred_free = await generate_predictions(matches, vip=False)
    if pred_free:
        msg = (
            f"╔═══════════════════════╗\n"
            f"║  🌅 *TIPS DU MATIN*  🌅 ║\n"
            f"║    📅 *{today}*    ║\n"
            f"╚═══════════════════════╝\n\n"
            f"{pred_free}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 *5 tips VIP disponibles !*\n"
            f"👉 Tape /start dans le bot"
        )
        try:
            await context.bot.send_message(FREE_CHANNEL, msg, parse_mode="Markdown")
            logger.info("✅ Tips FREE auto publiés.")
        except Exception as e:
            logger.error(f"❌ {e}")

    await asyncio.sleep(15)

    # VIP
    pred_vip = await generate_predictions(matches, vip=True)
    if pred_vip:
        msg = (
            f"╔═══════════════════════╗\n"
            f"║ 💎 *TIPS VIP EXCLUSIFS* ║\n"
            f"║    📅 *{today}*    ║\n"
            f"╚═══════════════════════╝\n\n"
            f"{pred_vip}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ _Pariez de façon responsable._\n"
            f"🏆 *STEPH PRONO* ⚡"
        )
        try:
            await context.bot.send_message(VIP_CHANNEL_ID, msg, parse_mode="Markdown")
            logger.info("✅ Tips VIP auto publiés.")
        except Exception as e:
            logger.error(f"❌ {e}")

# ============================================================
#  MAIN
# ============================================================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(btn_handler))
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(
            "^(⚽ Tips Gratuits|💎 Accès VIP|📊 Nos Résultats|ℹ️ À Propos|"
            "📤 Publier FREE|💎 Publier VIP|👥 Statistiques|🔧 Test IA)$"
        ),
        keyboard_handler
    ))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, msg_handler))

    app.job_queue.run_daily(
        auto_publish,
        time=datetime.strptime("09:00", "%H:%M").time()
    )

    logger.info("🚀 Bot STEPH PRONO V4 démarré !")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
