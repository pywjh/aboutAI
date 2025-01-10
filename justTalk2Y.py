# -*- coding: utf-8 -*-
"""
   File Name：     justTalk2Y
   Author :        bd
   date：          2025/1/10
"""
__author__ = 'bd'

import os

from openai import OpenAI

# api_key = "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"
openrouter_app_name = os.getenv('OPENROUTER_APP_NAME', 'A Free Model Test')
api_key = os.getenv('OPENAI_API_KEY', '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')
openrouter_http_referer = os.getenv('OPENROUTER_HTTP_REFERER', 'https://github.com')

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)


def chat(messages):
    # print(messages)
    completion = client.chat.completions.create(
        extra_headers={
            "HTTP-Referer": openrouter_http_referer,
            "X-Title": openrouter_app_name,
        },
        model="google/gemini-pro",
        # model="google/gemini-2.0-flash-thinking-exp:free",
        # messages=messages,
        messages=[
            {
                "role": "user",
                "content": messages
            }
        ]
    )

    if completion and completion.choices:
        content = completion.choices[0].message.content
        return content
    else:
        print(completion)
        return "出错啦，请重新再问一次吧～"


def add_new_question():
    question = []
    while True:
        _question = str(input(">>>: "))
        if not _question:
            continue
        question.append({
                "type": "text",
                "text": _question
            })
        # print(_question)
        answer = chat(question)
        print(answer)


if __name__ == '__main__':
    add_new_question()
    # s = chat(
    #     [
    #         {
    #             "role": "user",
    #             "content": [
    #                 {
    #                     "type": "text",
    #                     "text": "你这个模型的上下文要怎么传递？"
    #                 }
    #             ]
    #         }
    #     ]
    # )
    # print(s)
