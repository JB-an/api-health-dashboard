#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
取得更多 API ID
"""

import json
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

with open("collected_ids.json", "r", encoding="utf-8") as f:
    collected_ids = json.load(f)

base_url = config["base_url"]

session = requests.Session()
session.verify = False
session.headers.update({"Content-Type": "application/json"})

# Login
resp = session.post(f"{base_url}/api/app/users/Login", json={
    "TenantName": config["tenant"],
    "LoginId": config["account"],
    "Password": config["password"]
})
data = resp.json()
token = data.get("accessToken") or data.get("id4Token", {}).get("access_token")
session.headers["Authorization"] = f"Bearer {token}"
print("Login OK")

# 取得所有表單設計的詳細資訊 (包含 flowDesignId)
print("\n=== GetFormsDesignList (with more fields) ===")
resp = session.post(f"{base_url}/api/app/FlowEngine/form/GetFormsDesignList", json={
    "MaxResultCount": 100,
    "SkipCount": 0
})
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    items = data.get("items", []) if isinstance(data, dict) else data
    if items:
        first = items[0]
        print(f"Keys: {list(first.keys())}")
        if "flowDesignId" in first:
            collected_ids["flowDesignId"] = first["flowDesignId"]
            print(f"flowDesignId: {first['flowDesignId']}")

# 用 formsDesignCode 嘗試取得流程
print("\n=== GetProcessFlowView with correct params ===")
resp = session.post(f"{base_url}/api/app/FlowEngine/GetProcessFlowView", json={
    "MaxResultCount": 100,
    "SkipCount": 0,
    "FormDesignCode": collected_ids.get("formsDesignCode", ""),
    "ProcessFlowQueryRole": "Applicant",
    "Sorting": "creationTime desc"
})
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    items = data.get("items", [])
    print(f"Items: {len(items)}")
    if items:
        first = items[0]
        print(f"Keys: {list(first.keys())}")
        collected_ids["processFlowId"] = first.get("id")
        collected_ids["processId"] = first.get("processId")
        collected_ids["formsAppId"] = first.get("formsAppId")
else:
    print(f"Error: {resp.text[:300]}")

# 嘗試其他角色
for role in ["SignOff", "Agent", "All"]:
    print(f"\n=== GetProcessFlowView role={role} ===")
    resp = session.post(f"{base_url}/api/app/FlowEngine/GetProcessFlowView", json={
        "MaxResultCount": 10,
        "SkipCount": 0,
        "FormDesignCode": "",  # Empty to get all
        "ProcessFlowQueryRole": role
    })
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        items = data.get("items", [])
        print(f"Items: {len(items)}")
        if items and not collected_ids.get("processFlowId"):
            first = items[0]
            collected_ids["processFlowId"] = first.get("id")
            collected_ids["processId"] = first.get("processId")
            collected_ids["formsAppId"] = first.get("formsAppId")
            print(f"Found! processFlowId: {first.get('id')}")
            break

# 嘗試取得 flowNodeList
if collected_ids.get("flowDesignId"):
    print("\n=== GetFlowNodeList ===")
    resp = session.post(f"{base_url}/api/app/FlowEngine/Flow/GetFlowNodeList", json={
        "flowDesignId": collected_ids["flowDesignId"]
    })
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        if items:
            collected_ids["flowNodeId"] = items[0].get("id")
            print(f"flowNodeId: {collected_ids.get('flowNodeId')}")

print("\n" + "=" * 50)
print("=== ALL COLLECTED IDs ===")
print("=" * 50)
for k, v in collected_ids.items():
    print(f"{k}: {v}")

with open("collected_ids.json", "w", encoding="utf-8") as f:
    json.dump(collected_ids, f, ensure_ascii=False, indent=2)
print("\nSaved!")
