#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
取得真實 API ID 的腳本 - 完整版 v3
"""

import json
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 載入設定
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

base_url = config["base_url"]

session = requests.Session()
session.verify = False
session.headers.update({
    "Content-Type": "application/json",
    "Accept": "application/json"
})

# 登入
print("=== Login ===")
login_resp = session.post(f"{base_url}/api/app/users/Login", json={
    "TenantName": config["tenant"],
    "LoginId": config["account"],
    "Password": config["password"]
})

if login_resp.status_code == 200:
    data = login_resp.json()
    token = data.get("accessToken") or data.get("access_token") or data.get("id4Token", {}).get("access_token")
    session.headers["Authorization"] = f"Bearer {token}"
    print("OK!")
else:
    print(f"FAIL: {login_resp.status_code}")
    exit(1)

collected_ids = {}

# 1. NewGetFormsDesignList
print("\n=== NewGetFormsDesignList ===")
resp = session.post(f"{base_url}/api/app/FlowEngine/form/NewGetFormsDesignList", json={})
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    print(f"Type: {type(data)}")
    
    # Handle both list and dict response
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("items", [])
    else:
        items = []
    
    print(f"Items count: {len(items)}")
    if items:
        first_item = items[0]
        print(f"Keys: {list(first_item.keys())}")
        collected_ids["formsDesignId"] = first_item.get("id")
        collected_ids["formsDesignCode"] = first_item.get("code") or first_item.get("formsDesignCode")
        if first_item.get("flowDesignId"):
            collected_ids["flowDesignId"] = first_item.get("flowDesignId")

# 2. GetSystemBoardList
print("\n=== GetSystemBoardList ===")
resp = session.post(f"{base_url}/api/app/systems/GetSystemBoardList", json={
    "MaxResultCount": 10,
    "SkipCount": 0
})
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    items = data.get("items", [])
    if items:
        collected_ids["boardId"] = items[0].get("id")

# 3. GetApiCatalogList
print("\n=== GetApiCatalogList ===")
resp = session.post(f"{base_url}/api/app/apiCatalogs/GetApiCatalogList", json={
    "MaxResultCount": 10,
    "SkipCount": 0
})
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    items = data.get("items", [])
    if items:
        collected_ids["apiCatalogId"] = items[0].get("id")
        collected_ids["apiCatalogCode"] = items[0].get("code")

# 4. GetProcessFlowWaitSign - 取得待簽核
print("\n=== GetProcessFlowWaitSign ===")
resp = session.post(f"{base_url}/api/app/FlowEngine/GetProcessFlowWaitSign", json={
    "empCode": []
})
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    if isinstance(data, list):
        items = data
    else:
        items = data.get("items", [])
    print(f"Items count: {len(items)}")
    if items:
        first = items[0]
        print(f"Keys: {list(first.keys())}")
        collected_ids["processFlowId"] = first.get("id")
        collected_ids["formsAppId"] = first.get("formsAppId")

# 5. GetFlowByFormsDesign - 從表單設計取得流程設計
if collected_ids.get("formsDesignId"):
    print("\n=== GetFlowByFormsDesign ===")
    resp = session.post(f"{base_url}/api/app/FlowEngine/Flow/GetFlowByFormsDesign", json={
        "formsDesignId": collected_ids["formsDesignId"]
    })
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, dict):
            collected_ids["flowDesignId"] = data.get("id") or data.get("flowDesignId")
            print(f"flowDesignId: {collected_ids.get('flowDesignId')}")

# 6. 嘗試取得 ProcessFlowView (用正確的參數)
if collected_ids.get("formsDesignCode"):
    print("\n=== GetProcessFlowView ===")
    resp = session.post(f"{base_url}/api/app/FlowEngine/GetProcessFlowView", json={
        "MaxResultCount": 10,
        "SkipCount": 0,
        "FormDesignCode": collected_ids["formsDesignCode"],
        "ProcessFlowQueryRole": "Applicant"
    })
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        items = data.get("items", [])
        print(f"Items: {len(items)}")
        if items:
            first = items[0]
            collected_ids["processFlowId"] = first.get("id")
            collected_ids["processId"] = first.get("processId")

# 輸出收集到的 ID
print("\n" + "=" * 50)
print("=== COLLECTED IDs ===")
print("=" * 50)
for key, value in collected_ids.items():
    print(f"{key}: {value}")

# 儲存到檔案
with open("collected_ids.json", "w", encoding="utf-8") as f:
    json.dump(collected_ids, f, ensure_ascii=False, indent=2)
print("\nSaved to collected_ids.json")
