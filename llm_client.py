# -*- coding:utf-8 -*-

import os
import time
import requests
from openai import OpenAI
import sys
import time
import pathlib
import random
sys.path.append(str(pathlib.Path(__file__).parent))

def call_llm(messages, ip_port_list, model_type='', sampling_params=None):
    if sampling_params is None:
        sampling_params = {
            "top_p": 0.95,
            "top_k": -1,
            "temperature": 0.6,
            "max_tokens":65536
        }
    new_messages = []
    for message in messages:
        role = "assistant" if message["role"] == "model" else message["role"]
        new_messages.append({"role": role, "content": "\n".join(message["content"])})
    exception = None
    for _ in range(10):
        try:
            ip_port = random.choice(ip_port_list)
            url = f'http://{ip_port}/v1'
            client = OpenAI(base_url=url, api_key="token-abc123")
            if 'DeepSeekV3.1' in model_type:
                system = ''
                users = []
                assistants = []
                for msg in new_messages:
                    if msg['role'] == 'system':
                        system = msg['content']
                    elif msg['role'] == 'user':
                        users.append(msg['content'])
                    elif msg['role'] == 'assistant':
                        assistants.append(msg['content'])
                    else:
                        raise Exception('invalid role:' + msg['role'])
                assert len(users) == (len(assistants) + 1)
                prompt = f'<｜begin▁of▁sentence｜>{system}'
                for k in range(len(users)):
                    prompt += f'<｜User｜>{users[k]}'
                    if len(assistants) >= (k + 1):
                        prompt += f'<｜Assistant｜></think>{assistants[k]}<｜end▁of▁sentence｜>'
                prompt += '<｜Assistant｜><think>'
                completion = client.completions.create(
                    prompt=prompt,
                    model=None,
                    top_p=sampling_params["top_p"],
                    temperature=sampling_params["temperature"],
                    max_tokens=sampling_params["max_tokens"],
                    timeout=108000,
                    extra_body={
                        "top_k": sampling_params["top_k"]
                     }
                )
                vllm_obj = {
                    "prompt": prompt,
                    "status_code": 0,
                    "finish_reason": completion.choices[0].finish_reason,
                    "stop_reason": completion.choices[0].stop_reason,
                    "completion_tokens": completion.usage.completion_tokens,
                    "text": completion.choices[0].text
                }
            else:
                completion = client.chat.completions.create(
                messages=new_messages,
                model=None,
                top_p=sampling_params["top_p"],
                temperature=sampling_params["temperature"],
                max_tokens=sampling_params["max_tokens"],
                timeout=108000,
                extra_body={
                    "top_k": sampling_params["top_k"]
                }
                )
                vllm_obj = {
                "messages": new_messages,
                "status_code": 0,
                "finish_reason": completion.choices[0].finish_reason,
                "stop_reason": completion.choices[0].stop_reason,
                "completion_tokens": completion.usage.completion_tokens,
                "text": completion.choices[0].message.content
                }
            return vllm_obj
        except:
            import traceback
            exception = traceback.format_exc()
            print(exception)
            time.sleep(120)
    raise Exception(f"vllm error: {[exception]}")


if __name__ == '__main__':
    js = [{'role': 'system', 'content': ['Your name is GuaGua']}, {'role':
        'user', 'content': ['What is your name?']}]
    ip_port_list = ['29.201.150.224:8021','29.247.250.158:8021']
    print(call_llm(js, ip_port_list))
