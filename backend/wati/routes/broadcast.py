from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Request, Body, BackgroundTasks, Query, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse, Response
from ..models import Broadcast, Contacts, ChatBox
from ..models.ChatBox import Last_Conversation, Conversation
from ..Schemas import broadcast, user, chatbox
from ..database import database
from ..oauth2 import get_current_user
from ..crud.template import send_template_to_whatsapp
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, cast, String, update
from typing import AsyncGenerator
import httpx
import json
import csv
import io
import asyncio
import os
import logging
import dramatiq
from datetime import datetime
import google.generativeai as genai
import mimetypes
from urllib.parse import urlparse, unquote

from typing import Any

router = APIRouter(tags=["Broadcast"])

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEBHOOK_VERIFY_TOKEN = "12345"  # Replace with your verification token


# ...existing code...
@router.post("/generate_diwali_wish")
async def generate_diwali_wish(request: Request = None, prompt: Any = Body(None), q: str | None = Query(None)):
    """
    Accepts JSON {"prompt":"..."} or raw text or ?q=...
    Attempts to select a compatible generative model by listing available models
    and trying a short set of candidates. Returns readable errors.
    """
    try:
        # --- normalize prompt ---
        prompt_value = None
        if isinstance(prompt, str) and prompt.strip():
            prompt_value = prompt.strip()
        elif isinstance(prompt, dict):
            prompt_value = (prompt.get("prompt") or prompt.get("text") or "").strip() or None

        if not prompt_value and q:
            prompt_value = q.strip()

        if not prompt_value and request is not None:
            content_type = (request.headers.get("content-type") or "").lower()
            if "application/json" in content_type:
                try:
                    body = await request.json()
                    if isinstance(body, dict):
                        prompt_value = (body.get("prompt") or body.get("text") or "").strip() or None
                    elif isinstance(body, str) and body.strip():
                        prompt_value = body.strip()
                except Exception:
                    prompt_value = None
            elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
                form = await request.form()
                prompt_value = (form.get("prompt") or form.get("text") or "").strip() or None
            else:
                raw = await request.body()
                if raw:
                    decoded = raw.decode().strip()
                    prompt_value = decoded or None

        if not prompt_value:
            raise HTTPException(status_code=422, detail="Missing 'prompt' (body field or query param 'q')")

        if not GEMINI_API_KEY:
            logging.error("GEMINI_API_KEY not configured")
            return JSONResponse(status_code=500, content={"success": False, "error": "GEMINI_API_KEY not configured on server"})

       # ...existing code...
        genai.configure(api_key=GEMINI_API_KEY)

        # Simplify: use the free Gemini model (flash) only
        model_name = "models/gemini-2.5-flash"
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                f"Write a creative, warm WhatsApp Diwali wish for customers. Context: {prompt_value}"
            )
            wish = getattr(response, "text", None)
            if not wish:
                wish = response.candidates[0].content.parts[0].text
            return {"success": True, "wish": wish, "model_used": model_name}
        except Exception as e:
            logging.exception("Model %s failed: %s", model_name, e)
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": f"Model {model_name} failed",
                    "last_error": str(e),
                    "tried": [model_name]
                }
            )

       
        candidates = []
        model_support = {}

        if isinstance(models_resp, dict):
            models_list = models_resp.get("models") or models_resp.get("data") or []
        else:
            models_list = models_resp or []

        # Normalize model identifiers and capture supported generation methods
        for m in models_list:
            model_name = None
            supported_methods = []

            if isinstance(m, dict):
                for key in ("name", "id", "model", "model_name"):
                    if m.get(key):
                        model_name = str(m.get(key))
                        break
                supported_methods = m.get("supported_generation_methods") or m.get("supported_generation_methods") or []
            else:
                model_name = getattr(m, "name", None) or getattr(m, "id", None)
                supported_methods = getattr(m, "supported_generation_methods", []) or getattr(m, "supported_generation_methods", [])

            if model_name:
                candidates.append(str(model_name))
                model_support[str(model_name)] = list(supported_methods or [])

        # Add some fallback common names (kept at end)
        fallback_candidates = ["models/text-bison-001", "text-bison-001", "gpt-4o-mini", "gpt-4o", "models/gemini-2.5-flash", "models/gemini-2.5-pro"]
        for f in fallback_candidates:
            if f not in candidates:
                candidates.append(f)
                model_support[f] = []

        # Prefer models that advertise generateContent support
        prioritized = [name for name in candidates if "generateContent" in (model_support.get(name) or [])]

        # If none explicitly advertise generateContent, fall back to names matching known keywords
        if not prioritized:
            for c in candidates:
                lc = c.lower()
                if any(k in lc for k in ("bison", "gpt", "gemini", "gpt-4", "gpt-4o")):
                    prioritized.append(c)

        # ensure we have some candidates
        if not prioritized:
            prioritized = candidates[:6]

        # Try up to first 6 prioritized models to avoid long loops
        for model_name in prioritized[:6]:
            try:
                tried.append(model_name)
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(
                    f"Write a creative, warm WhatsApp Diwali wish for customers. Context: {prompt_value}"
                )
                # Extract text robustly
                wish = getattr(response, "text", None)
                if not wish:
                    # older response shape
                    wish = response.candidates[0].content.parts[0].text
                return {"success": True, "wish": wish, "model_used": model_name, "tried": tried}
            except Exception as e:
                last_exc = e
                logging.warning("Model %s failed: %s", model_name, str(e))
                continue

        logging.exception("All candidate models failed for generate_diwali_wish")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "No compatible generative model available. Tried models: " + ", ".join(prioritized[:6]),
                "last_error": str(last_exc),
                "tried": prioritized[:6]
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.exception("generate_diwali_wish unexpected error")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

# @router.post("/generate_diwali_wish")
# async def generate_diwali_wish(prompt: str = Body(...)):
#     try:
#         genai.configure(api_key=GEMINI_API_KEY)
#         model = genai.GenerativeModel("gemini-pro")
#         response = model.generate_content(
#             f"Write a creative, warm WhatsApp Diwali wish for customers. Context: {prompt} "
#         )
#         wish = getattr(response, "text", None) or response.candidates[0].content.parts[0].text
#         return {"success": True, "wish": wish}
#     except Exception as e:
#         return {"success": False, "error": str(e)}

@router.post("/broadcast/send_wish")
async def send_wish(message: str = Body(...)):
    print(f"Sending: {message}")
    return {"success": True, "sent_message": message}


# Meta Webhook verification endpoint
@router.get("/meta-webhook")
async def verify_webhook(request: Request):
    verify_token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    hubmode = request.query_params.get("hub.mode")
    if verify_token == WEBHOOK_VERIFY_TOKEN and hubmode == "subscribe":
        return PlainTextResponse(content=challenge or "", status_code=200)
    else:
        raise HTTPException(status_code=403, detail="Verification token mismatch")

# POST endpoint to handle webhook data from WhatsApp
@router.post("/meta-webhook")
async def receive_meta_webhook(request: Request, db: AsyncSession = Depends(database.get_db)):
    try:
        body = await request.json()
        logging.debug(json.dumps(body, indent=4))

        if "entry" not in body:
            raise HTTPException(status_code=400, detail="Invalid webhook format")

        for event in body["entry"]:
            if "changes" not in event:
                continue

            for change in event["changes"]:
                value = change.get("value", {})

                # Status updates
                if "statuses" in value:
                    for status in value["statuses"]:
                        wamid = status.get('id')
                        message_status = status.get("status")
                        message_read = message_delivered = message_sent = False
                        error_reason = None

                        if message_status == "read":
                            message_read = message_delivered = message_sent = True
                        elif message_status == "delivered":
                            message_delivered = message_sent = True
                        elif message_status == "sent":
                            message_sent = True
                        elif message_status == "failed":
                            if "errors" in status and status["errors"]:
                                error_details = status["errors"][0]
                                error_data_details = error_details.get("error_data", {}).get("details", "No details available")
                                error_reason = f"Error Code: {error_details.get('code', 'N/A')}, Title: {error_details.get('title', 'N/A')}, Details: {error_data_details}"

                        if wamid:
                            result1 = await db.execute(
                                select(Broadcast.BroadcastAnalysis).filter(Broadcast.BroadcastAnalysis.message_id == wamid)
                            )
                            broadcast_report = result1.scalars().first()
                            if broadcast_report:
                                broadcast_report.read = message_read
                                broadcast_report.delivered = message_delivered
                                broadcast_report.sent = message_sent
                                broadcast_report.status = message_status
                                if error_reason:
                                    broadcast_report.error_reason = error_reason
                                db.add(broadcast_report)
                                await db.commit()
                                await db.refresh(broadcast_report)

                # Messages (incoming / replies)
                if "messages" in value:
                    for message in value["messages"]:
                        if message.get('context', {}).get('id'):
                            wamid = message['context']['id']
                            result2 = await db.execute(
                                select(Broadcast.BroadcastAnalysis).filter(Broadcast.BroadcastAnalysis.message_id == wamid)
                            )
                            broadcast_report = result2.scalars().first()
                            if broadcast_report:
                                broadcast_report.replied = True
                                broadcast_report.sent = True
                                broadcast_report.status = "replied"
                                db.add(broadcast_report)
                                await db.commit()
                                await db.refresh(broadcast_report)

                # Handle incoming messages storage
                if "messages" in value:
                    await handle_incoming_messages(value, db)

        return {"message": "Webhook data received and processed successfully"}

    except KeyError as e:
        logging.error(f"Missing key in webhook payload: {e}")
        raise HTTPException(status_code=400, detail=f"Missing key: {e}")
    except Exception as e:
        logging.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def handle_incoming_messages(value: dict, db: AsyncSession):
    name = value.get('contacts', [{}])[0].get('profile', {}).get('name', 'unknown')
    for message in value.get("messages", []):
        wa_id = message.get('from')
        phone_number_id = value.get('metadata', {}).get('phone_number_id')
        message_id = message.get('id')
        message_content = message.get('text', {}).get('body', '')
        timestamp = int(message.get('timestamp', 0))
        message_type = message.get('type')
        context_message_id = message.get('context', {}).get('id')
        utc_time = datetime.utcfromtimestamp(timestamp) if timestamp else datetime.utcnow()

        result = await db.execute(select(Last_Conversation).filter(
            Last_Conversation.sender_wa_id == wa_id,
            Last_Conversation.receiver_wa_id == phone_number_id,
        ))
        last_conversation = result.scalars().first()

        if last_conversation:
            await db.delete(last_conversation)
            await db.commit()

        last_conv = Last_Conversation(
            business_account_id=value.get('metadata', {}).get('business_account_id', 'unknown'),
            message_id=message_id,
            message_content=message_content,
            sender_wa_id=wa_id,
            sender_name=name,
            receiver_wa_id=phone_number_id,
            last_chat_time=utc_time,
            active=True
        )
        db.add(last_conv)
        await db.commit()

        conversation = Conversation(
            wa_id=wa_id,
            message_id=message_id,
            phone_number_id=int(phone_number_id) if phone_number_id else None,
            message_content=message_content,
            timestamp=utc_time,
            context_message_id=context_message_id,
            message_type=message_type,
            direction="Receive"
        )
        db.add(conversation)
        await db.commit()


def convert_to_dict(instance):
    if instance is None:
        return None
    instance_dict = {}
    for key, value in instance.__dict__.items():
        if not key.startswith('_'):
            if isinstance(value, datetime):
                instance_dict[key] = value.isoformat()
            else:
                instance_dict[key] = value
    return instance_dict


@router.get("/sse/conversations/{contact_number}")
async def event_stream(
    contact_number: str,
    request: Request,
    background_tasks: BackgroundTasks,
    token: str = Query(...),
    db: AsyncSession = Depends(database.get_db),
) -> StreamingResponse:
    current_user = await get_current_user(token, db)
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    async def get_conversations() -> AsyncGenerator[str, None]:
        last_data = None
        while True:
            async with db.begin():
                result = await db.execute(
                    select(Conversation)
                    .filter(Conversation.wa_id == contact_number)
                    .filter(Conversation.phone_number_id == current_user.Phone_id)
                    .order_by(Conversation.timestamp)
                )
                conversations = result.scalars().all()

            conversation_data = [convert_to_dict(conversation) for conversation in conversations]

            if conversation_data != last_data:
                yield f"data: {json.dumps(conversation_data)}\n\n"
                last_data = conversation_data

            if await request.is_disconnected():
                break

            await asyncio.sleep(2)

    return StreamingResponse(get_conversations(), media_type="text/event-stream")


@router.get("/active-conversations")
async def get_active_conversations(
    request: Request,
    token: str = Query(...),
    db: AsyncSession = Depends(database.get_db),
) -> StreamingResponse:
    current_user = await get_current_user(token, db)
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    async def get_active_chats() -> AsyncGenerator[str, None]:
        last_active_chats = None
        while True:
            if await request.is_disconnected():
                break

            result = await db.execute(
                select(Last_Conversation)
                .filter(cast(Last_Conversation.receiver_wa_id, String) == str(current_user.Phone_id))
                .order_by(desc(Last_Conversation.last_chat_time))
            )
            active_chat_data = [convert_to_dict(chat) for chat in result.scalars().all()]

            if active_chat_data != last_active_chats:
                last_active_chats = active_chat_data
                yield f"data: {json.dumps(active_chat_data)}\n\n"

            await asyncio.sleep(1)

    return StreamingResponse(get_active_chats(), media_type="text/event-stream")


@router.post("/send-text-message-reply/")
async def send_text_message_reply(
    payload: chatbox.MessagePayload,
    db: AsyncSession = Depends(database.get_db),
    get_current_user: user.newuser = Depends(get_current_user)
):
    whatsapp_url = f"https://graph.facebook.com/v20.0/{get_current_user.Phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {get_current_user.PAccessToken}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": payload.wa_id,
        "context": {"message_id": payload.context_message_id},
        "type": "text",
        "text": {"preview_url": False, "body": payload.body}
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(whatsapp_url, headers=headers, json=data)

    if response.status_code != 200:
        logging.error(response.json())
        raise HTTPException(status_code=response.status_code, detail=response.json())

    response_data = response.json()
    try:
        conversation = Conversation(
            wa_id=payload.wa_id,
            message_id=response_data.get("messages")[0].get("id"),
            phone_number_id=get_current_user.Phone_id,
            message_content=payload.body,
            timestamp=datetime.utcnow(),
            context_message_id=payload.context_message_id,
            message_type="text",
            direction="sent"
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        return {"status": "Message sent", "response": response_data}
    except Exception as e:
        await db.rollback()
        logging.error(f"Error storing message: {e}")
        raise HTTPException(status_code=500, detail="Error storing message in database")


@router.post("/send-text-message/")
async def send_text_message(
    payload: chatbox.MessagePayload,
    db: AsyncSession = Depends(database.get_db),
    get_current_user: user.newuser = Depends(get_current_user)
):
    whatsapp_url = f"https://graph.facebook.com/v20.0/{get_current_user.Phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {get_current_user.PAccessToken}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": payload.wa_id,
        "type": "text",
        "text": {"body": payload.body}
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(whatsapp_url, headers=headers, json=data)

    if response.status_code != 200:
        logging.error(response.json())
        raise HTTPException(status_code=response.status_code, detail=response.json())

    response_data = response.json()
    try:
        conversation = Conversation(
            wa_id=payload.wa_id,
            message_id=response_data.get("messages")[0].get("id"),
            phone_number_id=get_current_user.Phone_id,
            message_content=payload.body,
            timestamp=datetime.utcnow(),
            context_message_id=None,
            message_type="text",
            direction="sent"
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        return {"status": "Message sent", "response": response_data}
    except Exception as e:
        await db.rollback()
        logging.error(f"Error storing message: {e}")
        raise HTTPException(status_code=500, detail="Error storing message in database")


@router.post("/send-template-message/")
async def send_template_message(
    request: broadcast.input_broadcast,
    get_current_user: user.newuser = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    broadcast_list = Broadcast.BroadcastList(
        user_id=get_current_user.id,
        name=request.name,
        template=request.template,
        contacts=[contact.phone for contact in request.recipients],
        type=request.type,
        success=0,
        failed=0,
        status="processing..."
    )
    db.add(broadcast_list)
    await db.commit()
    await db.refresh(broadcast_list)

    contacts_payload = [{"name": contact.name, "phone": contact.phone} for contact in request.recipients]
    send_template_messages_task.send(
        broadcast_id=broadcast_list.id,
        recipients=contacts_payload,
        template=request.template,
        template_data=request.template_data,
        image_id=request.image_id,
        body_parameters=request.body_parameters,
        phone_id=get_current_user.Phone_id,
        access_token=get_current_user.PAccessToken,
        user_id=get_current_user.id
    )

    return {"status": "processing", "broadcast_id": broadcast_list.id}


@dramatiq.actor
async def send_template_messages_task(
    broadcast_id: int,
    recipients: list,
    template: str,
    template_data: str,
    image_id: str,
    body_parameters: str,
    phone_id: str,
    access_token: str,
    user_id: int,
):
    async with database.get_db() as db:
        success_count = 0
        failed_count = 0
        errors = []
        API_url = f"https://graph.facebook.com/v20.0/{phone_id}/messages"
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        async with httpx.AsyncClient() as client:
            for contact in recipients:
                recipient_name = contact.get("name")
                recipient_phone = contact.get("phone")
                try:
                    template_json = json.loads(template_data) if template_data else {}
                except Exception:
                    template_json = {}
                Templatelanguage = template_json.get("language")

                data = {
                    "messaging_product": "whatsapp",
                    "to": recipient_phone,
                    "type": "template",
                    "template": {"name": template, "language": {"code": Templatelanguage}},
                }

                if image_id:
                    data["template"]["components"] = [{"type": "header", "parameters": [{"type": "image", "image": {"id": image_id}}]}]

                if body_parameters:
                    body_params = [{"type": "text", "text": f"{recipient_name}"}] if body_parameters == "Name" else []
                    data["template"].setdefault("components", []).append({"type": "body", "parameters": body_params})

                response = await client.post(API_url, headers=headers, json=data)
                response_data = response.json()

                if response.status_code == 200:
                    success_count += 1
                    wamid = response_data['messages'][0]['id']
                    phone_num = response_data['contacts'][0]["wa_id"]
                    message_log = Broadcast.BroadcastAnalysis(
                        user_id=user_id,
                        broadcast_id=broadcast_id,
                        message_id=wamid,
                        status="sent",
                        phone_no=phone_num,
                        contact_name=recipient_name,
                    )
                    db.add(message_log)
                    conversation = Conversation(
                        wa_id=recipient_phone,
                        message_id=wamid,
                        phone_number_id=phone_id,
                        message_content=f"#template_message# {template_json}",
                        timestamp=datetime.utcnow(),
                        context_message_id=None,
                        message_type="text",
                        direction="sent"
                    )
                    db.add(conversation)
                else:
                    failed_count += 1
                    errors.append({"recipient": recipient_phone, "error": response_data})
                    message_log = Broadcast.BroadcastAnalysis(
                        user_id=user_id,
                        broadcast_id=broadcast_id,
                        status="failed",
                        phone_no=recipient_phone,
                        contact_name=recipient_name,
                    )
                    db.add(message_log)

        await db.commit()
        result = await db.execute(select(Broadcast.BroadcastList).filter(Broadcast.BroadcastList.id == broadcast_id))
        broadcast_obj = result.scalars().first()
        if broadcast_obj:
            broadcast_obj.success = success_count
            broadcast_obj.status = "Successful" if failed_count == 0 else "Partially Successful"
            broadcast_obj.failed = failed_count
            await db.commit()


@router.get("/templates")
async def get_templates_list(get_current_user: user.newuser = Depends(get_current_user)):
    API_URL = f'https://graph.facebook.com/v15.0/{get_current_user.WABAID}/message_templates'
    headers = {'Authorization': f'Bearer {get_current_user.PAccessToken}'}
    async with httpx.AsyncClient() as client:
        response = await client.get(API_URL, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    data = response.json()
    template_names = [t.get('name') for t in data.get('data', [])]
    return JSONResponse(content=template_names)


@router.get("/template")
async def get_template_detail(get_current_user: user.newuser = Depends(get_current_user)):
    API_URL = f'https://graph.facebook.com/v15.0/{get_current_user.WABAID}/message_templates'
    headers = {'Authorization': f'Bearer {get_current_user.PAccessToken}'}
    async with httpx.AsyncClient() as client:
        response = await client.get(API_URL, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@router.post("/broadcast")
async def broadcast_create(
    request: broadcast.BroadcastListCreate,
    db: AsyncSession = Depends(database.get_db),
    get_current_user: user.newuser = Depends(get_current_user)
):
    broadcast_list = Broadcast.BroadcastList(
        user_id=get_current_user.id,
        name=request.name,
        template=request.template,
        contacts=request.contacts,
        type=request.type,
        success=0,
        failed=0,
        status="processing",
        scheduled_time=request.scheduled_time,
        task_id=request.task_id
    )
    db.add(broadcast_list)
    await db.commit()
    await db.refresh(broadcast_list)
    return {"broadcast_id": broadcast_list.id}


@router.get('/broadcast')
async def fetchbroadcastList(
    limit: int = Query(10),
    offset: int = Query(0),
    statusfilter: str | None = Query(None),
    tag: str | None = Query(None),
    db: AsyncSession = Depends(database.get_db),
    get_current_user: user.newuser = Depends(get_current_user)
):
    query = select(Broadcast.BroadcastList).filter(Broadcast.BroadcastList.user_id == get_current_user.id).order_by(desc(Broadcast.BroadcastList.id))
    if tag:
        query = query.filter(Broadcast.BroadcastList.template.ilike(f"%{tag}%"))
    if statusfilter and statusfilter != "null":
        query = query.filter(Broadcast.BroadcastList.status == statusfilter)
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    broadcast_list = result.scalars().all()
    if not broadcast_list:
        raise HTTPException(status_code=404, detail="No broadcasts found")
    return broadcast_list


@router.put("/broadcast/{broadcast_id}")
async def update_broadcast(
    broadcast_id: int,
    broadcast_update: broadcast.BroadcastListUpdate,
    db: AsyncSession = Depends(database.get_db),
    get_current_user: user.newuser = Depends(get_current_user)
):
    result = await db.execute(select(Broadcast.BroadcastList).where(Broadcast.BroadcastList.id == broadcast_id))
    broadcast_obj = result.scalar_one_or_none()
    if not broadcast_obj:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if broadcast_update.task_id:
        broadcast_obj.task_id = broadcast_update.task_id
    db.add(broadcast_obj)
    await db.commit()
    await db.refresh(broadcast_obj)
    return {"message": "Broadcast updated successfully", "broadcast_id": broadcast_id, "task_id": broadcast_obj.task_id}


@router.get("/scheduled-broadcast")
async def fetch_scheduled_broadcast_list(
    skip: int = 0, limit: int = 10, tag: str = None,
    db: AsyncSession = Depends(database.get_db),
    get_current_user: user.newuser = Depends(get_current_user)
):
    query = select(Broadcast.BroadcastList).where(Broadcast.BroadcastList.status == "Scheduled").order_by(Broadcast.BroadcastList.id.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    scheduled_broadcast_list = result.scalars().all()
    return scheduled_broadcast_list


@router.post("/import-contacts")
async def import_contacts(file: UploadFile = File(...), db: AsyncSession = Depends(database.get_db)):
    contents = await file.read()
    try:
        reader = csv.DictReader(io.StringIO(contents.decode("utf-8")))
        contacts = []
        for row in reader:
            contact = Contacts.Contact(name=row.get('name'), phone=row.get('phone'))
            contacts.append({"name": contact.name, "phone": contact.phone})
    except Exception as e:
        raise HTTPException(status_code=400, detail="Error reading or parsing CSV file.")
    return {"contacts": contacts}


@router.delete("/broadcasts-delete/{broadcast_id}")
async def delete_scheduled_broadcast(
    broadcast_id: int,
    db: AsyncSession = Depends(database.get_db),
    get_current_user: user.newuser = Depends(get_current_user)
):
    result = await db.execute(select(Broadcast.BroadcastList).filter(Broadcast.BroadcastList.id == broadcast_id))
    broadcast_obj = result.scalars().first()
    if not broadcast_obj:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    broadcast_obj.status = "Cancelled"
    await db.commit()
    return {"detail": "Scheduled broadcast has been canceled."}


@router.post("/create-template", response_model=broadcast.TemplateResponse)
async def create_template(request: broadcast.TemplateCreate, get_current_user: user.newuser = Depends(get_current_user)):
    try:
        template_data = request.dict()
        broadcast.TemplateCreate.validate_template(template_data)
        url = f"https://graph.facebook.com/v21.0/{get_current_user.WABAID}/message_templates"
        headers = {"Authorization": f"Bearer {get_current_user.PAccessToken}", "Content-Type": "application/json"}
        payload = template_data
        timeout = httpx.Timeout(30.0, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response_data = response.json()
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response_data)
        return response_data
    except HTTPException as e:
        logging.critical(f"HTTP Exception: {e.detail}")
        raise e


@router.delete("/delete-template/{template_name}")
async def DeleteTemplate(template_name: str, request: Request, get_current_user: user.newuser = Depends(get_current_user)):
    url = f"https://graph.facebook.com/v14.0/{get_current_user.WABAID}/message_templates?name={template_name}"
    headers = {"Authorization": f"Bearer {get_current_user.PAccessToken}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        response = await client.delete(url, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.json())
    return {"detail": "Template deleted successfully"}


@router.get("/broadcast-report/{broadcast_id}")
async def BroadcastReport(broadcast_id: int, get_current_user: user.newuser = Depends(get_current_user), db: AsyncSession = Depends(database.get_db)):
    query = select(Broadcast.BroadcastAnalysis).filter((Broadcast.BroadcastAnalysis.user_id == get_current_user.id) & (Broadcast.BroadcastAnalysis.broadcast_id == broadcast_id))
    result = await db.execute(query)
    broadcast_data = result.scalars().all()
    if not broadcast_data:
        raise HTTPException(status_code=404, detail="Broadcast data not found")
    return broadcast_data


@router.post("/upload-media")
async def upload_file(file: UploadFile = File(...), get_current_user: user.newuser = Depends(get_current_user), db: AsyncSession = Depends(database.get_db)):
    try:
        contents = await file.read()
    except Exception as e:
        logging.error(f"Error reading uploaded file: {e}")
        raise HTTPException(status_code=400, detail="Invalid file upload.")
    media_url = f"https://graph.facebook.com/v20.0/{get_current_user.Phone_id}/media"
    headers = {"Authorization": f"Bearer {get_current_user.PAccessToken}"}
    files = {'file': (file.filename, contents, file.content_type)}
    multipart_data = {'type': file.content_type.split("/")[0], 'messaging_product': 'whatsapp'}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(media_url, headers=headers, files=files, data=multipart_data, timeout=60.0)
        response_data = response.json()
        if response.status_code != 200:
            error_detail = response_data.get("error", {}).get("message", "Unknown error")
            logging.error(f"WhatsApp API error: {error_detail}")
            raise HTTPException(status_code=response.status_code, detail=error_detail)
        media_id = response_data.get("id")
        if not media_id:
            logging.error("Media ID not found in WhatsApp API response.")
            raise HTTPException(status_code=502, detail="Media ID not returned by WhatsApp API.")
        return JSONResponse(content={"filename": file.filename, "file_size": len(contents), "content_type": file.content_type, "whatsapp_media_id": media_id})
    except httpx.RequestError as e:
        logging.error(f"HTTP request failed: {e}")
        raise HTTPException(status_code=502, detail="Failed to connect to WhatsApp API.")
    except httpx.HTTPStatusError as e:
        logging.error(f"HTTP status error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while uploading the media.")


@router.get("/download-media/{media_id}")
async def load_media(media_id: str, get_current_user: user.newuser = Depends(get_current_user), db: AsyncSession = Depends(database.get_db)):
    try:
        response = await asyncio.to_thread(lambda: __import__("requests").get(f"https://graph.facebook.com/v20.0/{media_id}", headers={"Authorization": f"Bearer {get_current_user.PAccessToken}"}))
        if response.status_code != 200:
            raise HTTPException(status_code=404, detail="Media not found")
        media_url = response.json().get("url")
        if not media_url:
            raise HTTPException(status_code=404, detail="Unable to retrieve media URL")
        media_response = await asyncio.to_thread(lambda: __import__("requests").get(media_url, headers={"Authorization": f"Bearer {get_current_user.PAccessToken}"}))
        if media_response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to download media")
        content_type = media_response.headers.get("Content-Type", "application/octet-stream")
        extension = mimetypes.guess_extension(content_type) or ".bin"
        return Response(content=media_response.content, media_type=content_type, headers={"Content-Disposition": f"attachment; filename=downloaded_media{extension}"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download-media")
async def download_media(media_url: str = Query(..., description="URL of the media to download"), get_current_user: user.newuser = Depends(get_current_user)):
    headers = {"Authorization": f"Bearer {get_current_user.PAccessToken}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(media_url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch media")
        content_type = response.headers.get("content-type", "application/octet-stream")
        parsed_url = urlparse(media_url)
        filename = unquote(parsed_url.path.split("/")[-1].split("?")[0]) or "downloaded_media"
        if "." not in filename:
            ext = mimetypes.guess_extension(content_type) or ""
            filename += ext
        return StreamingResponse(io.BytesIO(response.content), media_type=content_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except httpx.RequestError as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching media: {str(exc)}")
# ...existing code...
