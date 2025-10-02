from fastapi import APIRouter, Depends, HTTPException, UploadFile, Request
from ..models import User
from ..Schemas import user
from ..database import database
from sqlalchemy.orm import Session
from .. import hashing
import secrets
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..oauth2 import get_current_user
import httpx
import requests
import json

router = APIRouter(tags=['User'])

# /subscribe_customer and other routes unchanged (not using CAPTCHA)

@router.post('/register')
async def new_user(
    request: user.register_user,
    db: AsyncSession = Depends(database.get_db)):

    # No Turnstile CAPTCHA logic
    # No call to verify_turnstile_token or check token

    # Check for existing user
    result = await db.execute(
        select(User.User).filter(
            (User.User.email == request.email)
        )
    )
    existing_user = result.scalars().first()
    
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Account with this email or phone number already exists"
        )
    
    # Create a new user
    api_key = secrets.token_hex(32)
    registeruser = User.User(
        username=request.username,
        email=request.email,
        password_hash=hashing.Hash.bcrypt(request.password),
        # WABAID=request.WABAID,
        # PAccessToken=request.PAccessToken,
        # Phone_id=request.Phone_id,
        api_key=api_key
    )
    
    db.add(registeruser)
    await db.commit()
    await db.refresh(registeruser)

    return {"success": True, "message": "Account created successfully"}

# Other endpoints unchanged

@router.post("/subscribe_customer")
async def process_responses(
    payload: dict,
    db: AsyncSession = Depends(database.get_db),
    get_current_user: user.newuser = Depends(get_current_user),
):
    sessionInfoResponse = payload.get("sessionInfoResponse")
    sdkResponse = payload.get("sdkResponse")
    if not sessionInfoResponse or not sdkResponse:
        raise HTTPException(status_code=400, detail="Missing required fields")
    try:
        session_info = json.loads(sessionInfoResponse)
        sdk_info = json.loads(sdkResponse)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    waba_id = session_info.get("data", {}).get("waba_id")
    code = sdk_info.get("authResponse", {}).get("code")
    if not waba_id or not code:
        raise HTTPException(status_code=400, detail="Invalid data received")
    current_user = await db.execute(
        select(User.User).filter(
            User.User.id == get_current_user.id
        )
    )
    current_user = current_user.scalars().first()
    if not current_user:
        raise HTTPException(
            status_code=400, detail="user not found"
        )
    token_url = "https://graph.facebook.com/v20.0/oauth/access_token"
    client_id = "2621821927998797"
    client_secret = "70f8ff2327df71cf505b853f0fdc4a20"
    redirect_uri = "https://2f4d-2405-201-3004-d09d-700c-69d4-6511-ab75.ngrok-free.app/broadcast/broadcast2"
    try:
        response = requests.post(
            token_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
            },
        )
        response.raise_for_status()
        token_data = response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to exchange code: {e}")
    current_user.WABAID = int(waba_id)
    current_user.PAccessToken = token_data.get("access_token")
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    Paccess_token = token_data.get("access_token")
    url = f"https://graph.facebook.com/v21.0/{waba_id}/subscribed_apps"
    headers = {
        "Authorization": f"Bearer {Paccess_token}",
    }
    response = requests.post(url, headers=headers)
    response.raise_for_status()
    return {"access_token": token_data.get("access_token"), "expires_in": token_data.get("expires_in")}

@router.post("/update-profile", status_code=200)
def update_profile(
    request: user.BusinessProfile, 
    get_current_user: user.newuser = Depends(get_current_user)
):
    WHATSAPP_API_URL = f"https://graph.facebook.com/v20.0/{get_current_user.Phone_id}/whatsapp_business_profile"
    payload = {
        "messaging_product": request.messaging_product,
        "address": request.address,
        "description": request.description,
        "vertical": request.vertical,
        "about": request.about,
        "email": str(request.email),
        "websites": [str(url) for url in request.websites],
        "profile_picture_handle": request.profile_picture_handle or None,
    }
    headers = {
        "Authorization": f"Bearer {get_current_user.PAccessToken}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(WHATSAPP_API_URL, json=payload, headers=headers)
        if response.status_code == 200:
            return {"message": "Business profile updated successfully", "data": response.json()}
        else:
            if response.headers.get("Content-Type") == "application/json":
                error_message = response.json().get("error", {}).get("message", "Unknown error occurred")
            else:
                error_message = response.text or "Unknown error occurred"
            raise HTTPException(
                status_code=response.status_code,
                detail=f"{error_message}",
            )
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {e}")

@router.post("/resumable-upload/")
async def resumable_upload(file: UploadFile, get_current_user: user.newuser = Depends(get_current_user)):
    BASE_URL = "https://graph.facebook.com/v20.0"
    ACCESS_TOKEN = get_current_user.PAccessToken
    file_content = await file.read()
    file_length = len(file_content)
    file_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
    file_name = file.filename
    create_session_url = f"{BASE_URL}/app/uploads/"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }
    params = {
        "file_length": file_length,
        "file_type": file_type,
        "file_name": file_name
    }
    create_session_response = requests.post(create_session_url, headers=headers, params=params)
    if create_session_response.status_code != 200:
        raise HTTPException(status_code=create_session_response.status_code, detail=create_session_response.json())
    upload_session_data = create_session_response.json()
    upload_id = upload_session_data["id"]
    upload_url = f"{BASE_URL}/{upload_id}&access_token={ACCESS_TOKEN}"
    upload_headers = {
        'Content-Type': 'image/jpeg',
        'Accept': '*/*',
        'file_offset': str(0)
    }
    payload = file_content
    upload_response = requests.post(upload_url, headers=upload_headers, data=payload)
    if upload_response.status_code != 200:
        raise HTTPException(status_code=upload_response.status_code, detail=upload_response.json())
    url = f"https://graph.facebook.com/v20.0/{upload_id}&access_token={ACCESS_TOKEN}"
    payload = file_content
    headers = {
        'Content-Type': 'image/jpeg',
        'file_offset': '0'
    }
    upload_response = requests.request("POST", url, headers=headers, data=payload)
    if upload_response.status_code != 200:
        raise HTTPException(status_code=upload_response.status_code, detail=upload_response.json())
    query_url = f"{BASE_URL}/{upload_id}&access_token={ACCESS_TOKEN}"
    query_response = requests.get(query_url, headers=headers)
    if query_response.status_code != 200:
        raise HTTPException(status_code=query_response.status_code, detail=query_response.json())
    return {
        "upload_session": upload_session_data,
        "upload_response": upload_response.json(),
        "query_status": query_response.json()
    }

@router.get("/get-business-profile/")
def get_business_profile(get_current_user: user.newuser = Depends(get_current_user)):
    BASE_URL = "https://graph.facebook.com/v17.0"
    ACCESS_TOKEN = get_current_user.PAccessToken
    PHONE_NUMBER_ID = get_current_user.Phone_id
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_business_profile?fields=about,address,description,email,profile_picture_url,websites,vertical"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.json())
    return response.json()
