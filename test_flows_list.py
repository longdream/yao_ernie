#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试flows/list接口"""
import requests
import json

response = requests.get('http://127.0.0.1:8765/flows/list')
data = response.json()

print(f"Success: {data['success']}")
print(f"Count: {data['count']}")
print(f"Flows returned: {len(data['flows'])}")

if data['count'] != len(data['flows']):
    print(f"WARNING: count ({data['count']}) != actual flows ({len(data['flows'])})")

# 显示所有flow_id
print("\nAll flow_ids:")
for i, flow in enumerate(data['flows'], 1):
    print(f"{i}. {flow['flow_id']} - {flow.get('task_description', '')[:50]}")

