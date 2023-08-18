#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2023/8/17
@Author  : mashenquan
@File    : azure_tts.py
@Desc    : azure TTS OAS3 api, which provides text-to-speech functionality
"""
from pathlib import Path
from uuid import uuid4
import base64
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))  # fix-bug: No module named 'metagpt'
from metagpt.utils.common import initialize_environment
from metagpt.logs import logger

from azure.cognitiveservices.speech import AudioConfig, SpeechConfig, SpeechSynthesizer
import os


class AzureTTS:
    """Azure Text-to-Speech"""

    def __init__(self, subscription_key, region):
        """
        :param subscription_key: key is used to access your Azure AI service API, see: `https://portal.azure.com/` > `Resource Management` > `Keys and Endpoint`
        :param region: This is the location (or region) of your resource. You may need to use this field when making calls to this API.
        """
        self.subscription_key = subscription_key if subscription_key else os.environ.get('AZURE_TTS_SUBSCRIPTION_KEY')
        self.region = region if region else os.environ.get('AZURE_TTS_REGION')

    # 参数参考：https://learn.microsoft.com/zh-cn/azure/cognitive-services/speech-service/language-support?tabs=tts#voice-styles-and-roles
    def synthesize_speech(self, lang, voice, text, output_file):
        speech_config = SpeechConfig(
            subscription=self.subscription_key, region=self.region)
        speech_config.speech_synthesis_voice_name = voice
        audio_config = AudioConfig(filename=output_file)
        synthesizer = SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config)

        # More detail: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice
        ssml_string = "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' " \
                      f"xml:lang='{lang}' xmlns:mstts='http://www.w3.org/2001/mstts'>" \
                      f"<voice name='{voice}'>{text}</voice></speak>"

        return synthesizer.speak_ssml_async(ssml_string).get()

    @staticmethod
    def role_style_text(role, style, text):
        return f'<mstts:express-as role="{role}" style="{style}">{text}</mstts:express-as>'

    @staticmethod
    def role_text(role, text):
        return f'<mstts:express-as role="{role}">{text}</mstts:express-as>'

    @staticmethod
    def style_text(style, text):
        return f'<mstts:express-as style="{style}">{text}</mstts:express-as>'


# Export
def oas3_azsure_tts(text, lang="", voice="", style="", role="", subscription_key="", region=""):
    """oas3/tts/azsure
    For more details, check out:`https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts`

    :param lang: The value can contain a language code such as en (English), or a locale such as en-US (English - United States). For more details, checkout: `https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts`
    :param voice: For more details, checkout: `https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts`, `https://speech.microsoft.com/portal/voicegallery`
    :param style: Speaking style to express different emotions like cheerfulness, empathy, and calm. For more details, checkout: `https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts`
    :param role: With roles, the same voice can act as a different age and gender. For more details, checkout: `https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts`
    :param text: The text used for voice conversion.
    :param subscription_key: key is used to access your Azure AI service API, see: `https://portal.azure.com/` > `Resource Management` > `Keys and Endpoint`
    :param region: This is the location (or region) of your resource. You may need to use this field when making calls to this API.
    :return: Returns the Base64-encoded .wav file data if successful, otherwise an empty string.

    """
    if not text:
        return ""

    if not lang:
        lang = "zh-CN"
    if not voice:
        voice = "zh-CN-XiaomoNeural"
    if not role:
        role = "Girl"
    if not style:
        style = "affectionate"
    if not subscription_key:
        subscription_key = os.environ.get("AZURE_TTS_SUBSCRIPTION_KEY")
    if not region:
        region = os.environ.get("AZURE_TTS_REGION")

    xml_value = AzureTTS.role_style_text(role=role, style=style, text=text)
    tts = AzureTTS(subscription_key=subscription_key, region=region)
    filename = Path(__file__).resolve().parent / (str(uuid4()).replace("-", "") + ".wav")
    try:
        tts.synthesize_speech(lang=lang, voice=voice, text=xml_value, output_file=str(filename))
        with open(str(filename), mode="rb") as reader:
            data = reader.read()
            base64_string = base64.b64encode(data).decode('utf-8')
        filename.unlink()
    except Exception as e:
        logger.error(f"text:{text}, error:{e}")
        return ""

    return base64_string


if __name__ == "__main__":
    initalize_enviroment()

    v = oas3_azsure_tts("测试，test")
    print(v)