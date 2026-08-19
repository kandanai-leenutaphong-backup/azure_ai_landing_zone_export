import base64
import ipaddress
import json
import os
import socket
import time

import requests
import streamlit as st
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient


# --------------- TCP helpers ---------------

def tcp_connectivity_test(ip: str, port: int, timeout: float) -> tuple[bool, str]:
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	sock.settimeout(timeout)
	try:
		code = sock.connect_ex((ip, port))
		if code == 0:
			return True, f"TCP connection to {ip}:{port} succeeded"
		return False, f"TCP connection to {ip}:{port} failed (error code: {code})"
	except Exception as exc:
		return False, f"TCP connection to {ip}:{port} failed ({exc})"
	finally:
		sock.close()


# --------------- Backend API helpers ---------------

DEFAULT_BASE_URL = os.getenv("BASE_URL", "https://be-app")


def get_easy_auth_token() -> str | None:
	"""Get the user's access token from Easy Auth headers (when deployed to Azure)."""
	try:
		headers = st.context.headers
		# Azure Container Apps Easy Auth injects token in this header
		return headers.get("X-Ms-Token-Aad-Access-Token")
	except Exception:
		return None


def call_endpoint(url: str, access_token: str, timeout: int = 20) -> requests.Response:
	headers = {"Authorization": f"Bearer {access_token}"}
	return requests.get(url, headers=headers, timeout=timeout)


def decode_jwt_claims(access_token: str) -> dict:
	try:
		parts = access_token.split(".")
		if len(parts) < 2:
			return {}
		payload = parts[1]
		padding = "=" * (-len(payload) % 4)
		decoded = base64.urlsafe_b64decode(payload + padding)
		return json.loads(decoded.decode("utf-8"))
	except Exception:
		return {}


# --------------- Streamlit UI ---------------

st.set_page_config(page_title="IP Test Tool", page_icon="🌐", layout="centered")
st.title("IP Test Tool")
st.write("Enter two IP addresses and press **Test**.")

ip_1 = st.text_input("IP Address 1", value="10.0.0.4")
ip_2 = st.text_input("IP Address 2", value="10.0.1.4")
cidr = st.number_input("CIDR for same-network check", min_value=1, max_value=32, value=16)
port = st.number_input("TCP port for reachability test", min_value=1, max_value=65535, value=22)
timeout = st.number_input("Timeout (seconds)", min_value=0.5, max_value=30.0, value=2.0, step=0.5)

if st.button("Test"):
	try:
		ip1_obj = ipaddress.ip_address(ip_1)
		ip2_obj = ipaddress.ip_address(ip_2)
	except ValueError as exc:
		st.error(f"Invalid IP address input: {exc}")
		st.stop()

	network_1 = ipaddress.ip_network(f"{ip_1}/{cidr}", strict=False)
	network_2 = ipaddress.ip_network(f"{ip_2}/{cidr}", strict=False)
	same_network = network_1.network_address == network_2.network_address

	st.subheader("Validation")
	st.success(f"IP 1 is valid: {ip1_obj}")
	st.success(f"IP 2 is valid: {ip2_obj}")

	st.subheader("Network Check")
	st.write(f"IP 1 network (/{cidr}): {network_1}")
	st.write(f"IP 2 network (/{cidr}): {network_2}")
	if same_network:
		st.success("Both IPs are in the same network for the selected CIDR.")
	else:
		st.warning("IPs are in different networks for the selected CIDR.")

	st.subheader("TCP Reachability")
	ok_1, message_1 = tcp_connectivity_test(ip_1, int(port), float(timeout))
	ok_2, message_2 = tcp_connectivity_test(ip_2, int(port), float(timeout))

	if ok_1:
		st.success(message_1)
	else:
		st.error(message_1)

	if ok_2:
		st.success(message_2)
	else:
		st.error(message_2)


# # --------------- Backend API Call Section ---------------

# st.divider()
# st.header("Backend API Call")
# st.write("Call an Azure Container Apps backend endpoint.")

# base_url = st.text_input("Base URL", value=DEFAULT_BASE_URL)
# manual_token = st.text_input("Access Token (optional – auto-detected from Easy Auth when deployed)", type="password")

# if st.button("Call Backend"):
# 	token = None
# 	token_source = None

# 	# Try sources in order: manual > env var > Easy Auth header
# 	if manual_token:
# 		token = manual_token
# 		token_source = "manual input"
# 	elif os.getenv("ACCESS_TOKEN"):
# 		token = os.getenv("ACCESS_TOKEN")
# 		token_source = "ACCESS_TOKEN env var"
# 	else:
# 		token = get_easy_auth_token()
# 		if token:
# 			token_source = "Easy Auth (X-Ms-Token-Aad-Access-Token header)"
# 		else:
# 			st.error(
# 				"No access token available.\n\n"
# 				"**When deployed:** Ensure Easy Auth is configured on this Container App "
# 				"and the user is logged in.\n\n"
# 				"**For local testing:** Paste a token manually or set ACCESS_TOKEN env var."
# 			)
# 			st.stop()

# 	st.info(f"Token acquired via: **{token_source}**")

# 	# --- JWT claims ---
# 	claims = decode_jwt_claims(token)
# 	if claims:
# 		with st.expander("Token claims"):
# 			st.json({
# 				"aud": claims.get("aud"),
# 				"iss": claims.get("iss"),
# 				"tid": claims.get("tid"),
# 				"appid/azp": claims.get("appid") or claims.get("azp"),
# 				"oid/sub": claims.get("oid") or claims.get("sub"),
# 				"scp": claims.get("scp"),
# 				"roles": claims.get("roles"),
# 			})

# 	# --- main endpoint ---
# 	with st.spinner("Calling backend…"):
# 		start = time.perf_counter()
# 		response = call_endpoint(base_url, token)
# 		elapsed_ms = (time.perf_counter() - start) * 1000

# 	st.subheader("Endpoint Response")
# 	if response.status_code < 400:
# 		st.success(f"**{response.status_code}** — {elapsed_ms:.1f} ms")
# 	else:
# 		st.error(f"**{response.status_code}** — {elapsed_ms:.1f} ms")

# 	st.write(f"**Content-Type:** {response.headers.get('content-type')}")
# 	st.code(response.text[:800], language="json")

# 	# --- .auth/me diagnostics ---
# 	auth_me_url = f"{base_url.rstrip('/')}/.auth/me"
# 	auth_me_response = call_endpoint(auth_me_url, token)
# 	with st.expander("Auth diagnostics (.auth/me)"):
# 		st.write(f"**URL:** {auth_me_url}")
# 		st.write(f"**Status:** {auth_me_response.status_code}")
# 		st.code(auth_me_response.text[:800], language="json")

# 	# --- troubleshooting hints ---
# 	if response.status_code == 401:
# 		st.warning(
# 			"**401 Unauthorized** – token/audience mismatch.\n\n"
# 			"Check:\n"
# 			"1. Entra app registration → Expose an API → Application ID URI and scope.\n"
# 			"2. Container Apps Authentication → allowed token audiences.\n"
# 			"3. Frontend app has API permission to call the backend."
# 		)
# 	elif response.status_code == 403:
# 		st.warning(
# 			"**403 Forbidden** – token accepted but authorization denied.\n\n"
# 			"Check:\n"
# 			"1. Container App Authentication → Authorization policy.\n"
# 			"2. User/app has required role assignments."
# 		)


# --------------- Public Backend (HTML) Section ---------------

DEFAULT_PUBLIC_URL = os.getenv("PUBLIC_BACKEND_URL", "https://be-app2")

st.divider()
st.header("Public Backend (HTML)")
st.write("Fetch HTML content from a public backend endpoint (no auth required).")

public_url = st.text_input("Public Backend URL", value=DEFAULT_PUBLIC_URL)
public_timeout = st.number_input("Request Timeout (seconds)", min_value=1, max_value=60, value=10)

if st.button("Fetch HTML"):
	with st.spinner("Fetching…"):
		start = time.perf_counter()
		try:
			response = requests.get(public_url, timeout=public_timeout)
			elapsed_ms = (time.perf_counter() - start) * 1000
		except requests.RequestException as exc:
			st.error(f"Request failed: {exc}")
			st.stop()

	if response.status_code < 400:
		st.success(f"**{response.status_code}** — {elapsed_ms:.1f} ms")
	else:
		st.error(f"**{response.status_code}** — {elapsed_ms:.1f} ms")

	st.write(f"**Content-Type:** {response.headers.get('content-type', 'unknown')}")

	content_type = response.headers.get("content-type", "")
	if "html" in content_type:
		with st.expander("Raw HTML", expanded=False):
			st.code(response.text, language="html")
		st.subheader("Rendered HTML")
		st.html(response.text)
	else:
		st.subheader("Response Body")
		st.code(response.text[:2000], language="text")


# --------------- Azure Blob Storage Section ---------------

DEFAULT_STORAGE_ACCOUNT = os.getenv("STORAGE_ACCOUNT_URL", "")
DEFAULT_CONTAINER = os.getenv("STORAGE_CONTAINER", "test")

st.divider()
st.header("Azure Blob Storage Test")
st.write("Test connectivity to Azure Blob Storage using Managed Identity.")

storage_account_url = st.text_input("Storage Account URL", value=DEFAULT_STORAGE_ACCOUNT)
container_name = st.text_input("Container Name", value=DEFAULT_CONTAINER)

if st.button("List Blobs", key="list_blobs_public"):
	with st.spinner("Connecting to storage…"):
		try:
			credential = DefaultAzureCredential()
			client = BlobServiceClient(
				account_url=storage_account_url,
				credential=credential
			)
			container_client = client.get_container_client(container_name)

			blobs = list(container_client.list_blobs())
			st.success(f"Connected successfully! Found **{len(blobs)}** blob(s).")

			if blobs:
				st.subheader("Blobs in container")
				for blob in blobs:
					st.write(f"- `{blob.name}` ({blob.size} bytes)")
			else:
				st.info("Container is empty.")

		except Exception as exc:
			st.error(f"Storage connection failed:\n\n{exc}")


# --------------- Private Azure Blob Storage Section ---------------

DEFAULT_PRIV_STORAGE_ACCOUNT = os.getenv("PRIV_STORAGE_ACCOUNT_URL", "")
DEFAULT_PRIV_CONTAINER = os.getenv("PRIV_STORAGE_CONTAINER", "test")

st.divider()
st.header("Private Azure Blob Storage Test")
st.write("Test connectivity to private Azure Blob Storage using Managed Identity.")

priv_storage_account_url = st.text_input("Private Storage Account URL", value=DEFAULT_PRIV_STORAGE_ACCOUNT)
priv_container_name = st.text_input("Private Container Name", value=DEFAULT_PRIV_CONTAINER)

if st.button("List Blobs (Private)", key="list_blobs_private"):
	with st.spinner("Connecting to private storage…"):
		try:
			credential = DefaultAzureCredential()
			client = BlobServiceClient(
				account_url=priv_storage_account_url,
				credential=credential
			)
			container_client = client.get_container_client(priv_container_name)

			blobs = list(container_client.list_blobs())
			st.success(f"Connected successfully! Found **{len(blobs)}** blob(s).")

			if blobs:
				st.subheader("Blobs in private container")
				for blob in blobs:
					st.write(f"- `{blob.name}` ({blob.size} bytes)")
			else:
				st.info("Container is empty.")

		except Exception as exc:
			st.error(f"Private storage connection failed:\n\n{exc}")








# --------------- Azure Blob Storage Section uami ---------------

DEFAULT_STORAGE_ACCOUNT = os.getenv("STORAGE_ACCOUNT_URL", "")
DEFAULT_CONTAINER = os.getenv("STORAGE_CONTAINER", "test")

st.divider()
st.header("Azure Blob Storage Test - uami")
st.write("Test connectivity to Azure Blob Storage using Managed Identity.")

storage_account_url = st.text_input("Storage Account URL uami", value=DEFAULT_STORAGE_ACCOUNT)
container_name = st.text_input("Container Name uami", value=DEFAULT_CONTAINER)

if st.button("List Blobs uami", key="list_blobs_uami"):
	with st.spinner("Connecting to storage…"):
		try:
			credential = DefaultAzureCredential()
			client = BlobServiceClient(
				account_url=storage_account_url,
				credential=credential
			)
			container_client = client.get_container_client(container_name)

			blobs = list(container_client.list_blobs())
			st.success(f"Connected successfully! Found **{len(blobs)}** blob(s).")

			if blobs:
				st.subheader("Blobs in container")
				for blob in blobs:
					st.write(f"- `{blob.name}` ({blob.size} bytes)")
			else:
				st.info("Container is empty.")

		except Exception as exc:
			st.error(f"Storage connection failed:\n\n{exc}")


# --------------- Private Azure Blob Storage Section ---------------

DEFAULT_PRIV_STORAGE_ACCOUNT = os.getenv("PRIV_STORAGE_ACCOUNT_URL", "")
DEFAULT_PRIV_CONTAINER = os.getenv("PRIV_STORAGE_CONTAINER", "test")

st.divider()
st.header("Private Azure Blob Storage Test - uami")
st.write("Test connectivity to private Azure Blob Storage using Managed Identity.")

priv_storage_account_url = st.text_input("Private Storage Account URL Uami", value=DEFAULT_PRIV_STORAGE_ACCOUNT)
priv_container_name = st.text_input("Private Container Name uami", value=DEFAULT_PRIV_CONTAINER)

if st.button("List Blobs (Private) uami", key="list_blobs_private_uami"):
	with st.spinner("Connecting to private storage…"):
		try:
			credential = DefaultAzureCredential()
			client = BlobServiceClient(
				account_url=priv_storage_account_url,
				credential=credential
			)
			container_client = client.get_container_client(priv_container_name)

			blobs = list(container_client.list_blobs())
			st.success(f"Connected successfully! Found **{len(blobs)}** blob(s).")

			if blobs:
				st.subheader("Blobs in private container")
				for blob in blobs:
					st.write(f"- `{blob.name}` ({blob.size} bytes)")
			else:
				st.info("Container is empty.")

		except Exception as exc:
			st.error(f"Private storage connection failed:\n\n{exc}")