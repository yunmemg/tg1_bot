from telethon.sync import TelegramClient
from telethon.errors import SessionPasswordNeededError, PasswordHashInvalidError
import json
import re
import zipfile
import os
import random
import requests
from datetime import datetime

# ==================== 配置参数 ====================
api_id = 33059943
api_hash = '1c73a0510ba0b8cb3bd16f24acfd62bf'
app_version = '1.8.9.4(46584)'  # 默认值，后续会被随机覆盖
system_lang_code = 'en-US'      # 默认值，后续会被随机覆盖

# ==================== 环境随机池 ====================
# 设备类型池
设备类型池 = ['Desktop', 'SMARTPHONE', 'Pad']

# 型号前缀池
型号前缀池 = ['K', 'Z', 'A', 'T', 'U', 'P', 'M', 'S', 'Q']

# 型号池
型号池 = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
          '20', '30', '40', '50', '60', '70', '80', '90', '100']

# 尾缀池
尾缀池 = ['i', 'E', 'Pro', 'ProMax']

# 版本池
版本池 = ['5G', '4G']

# 系统版本池（按设备类型分类）
# Windows 版本
windows_versions = [
    'Windows 10', 'Windows 11', 'Windows 8.1', 'Windows 8',
    'Windows 7', 'Windows Server 2016', 'Windows Server 2019',
    'Windows Server 2022', 'Windows 10 Pro', 'Windows 11 Pro'
]

# Linux 版本
linux_versions = [
    'Ubuntu 20.04', 'Ubuntu 22.04', 'Ubuntu 24.04',
    'Debian 11', 'Debian 12', 'Fedora 36', 'Fedora 37',
    'CentOS 7', 'CentOS 8', 'Arch Linux'
]

# macOS 版本
macos_versions = [
    'macOS 12 Monterey', 'macOS 13 Ventura', 'macOS 14 Sonoma',
    'macOS 15 Sequoia'
]

# Android 版本
android_versions = [
    'Android 12', 'Android 13', 'Android 14', 'Android 15',
    'Android 11', 'Android 10', 'Android 9'
]

# iOS 版本（至少10条）
ios_versions = [
    'iOS 15.0', 'iOS 15.5', 'iOS 16.0', 'iOS 16.1', 'iOS 16.2',
    'iOS 17.0', 'iOS 17.1', 'iOS 17.2', 'iOS 18.0', 'iOS 18.1'
]

# 应用版本池
app_versions = [
    '1.8.9.4(46584)', '1.9.0.1(46800)', '1.9.1.2(47000)',
    '2.0.0.1(47500)', '2.1.0.1(48000)', '2.2.0.1(48500)'
]

# 语言代码池
system_lang_codes = ['en-US', 'ru-RU', 'zh-CN', 'es-ES', 'de-DE', 'fr-FR']

# ==================== 环境生成函数 ====================
def 生成环境配置():
    """随机生成设备型号、系统版本、应用版本、语言等"""
    # 随机选择设备类型
    device_type = random.choice(设备类型池)
    
    # 生成设备型号（沿用原逻辑）
    型号前缀 = random.choice(型号前缀池)
    型号 = random.choice(型号池)
    尾缀 = random.choice(尾缀池)
    版本 = random.choice(版本池)
    device_model = f'WitchMagic {device_type} {型号前缀}{型号}{尾缀} {版本}'
    
    # 根据设备类型选择系统版本
    if device_type == 'Desktop':
        # 桌面系统池合并 Windows/Linux/macOS
        desktop_versions = windows_versions + linux_versions + macos_versions
        system_version = random.choice(desktop_versions)
    elif device_type == 'SMARTPHONE':
        # 手机系统池合并 Android/iOS
        smartphone_versions = android_versions + ios_versions
        system_version = random.choice(smartphone_versions)
    else:  # Pad
        # 平板系统池：iOS 或 Android 平板版（这里用 iOS 或 Android 版本代替）
        pad_versions = ios_versions + android_versions
        system_version = random.choice(pad_versions)
    
    # 随机选择应用版本
    app_version = random.choice(app_versions)
    
    # 随机选择语言配置
    system_lang_code = random.choice(system_lang_codes)
    
    return {
        'device_model': device_model,
        'system_version': system_version,
        'app_version': app_version,
        'system_lang_code': system_lang_code,
        'lang_pack': 'en'  # 保留 lang_pack 用于 JSON 记录，不传给客户端
    }

# ==================== 辅助函数 ====================
def 处理格式(手机号):
    """处理手机号格式，移除非数字字符"""
    return re.sub(r'\D', '', 手机号)

def 获取IP信息():
    """通过 ping0.cc/geo 获取当前IP信息"""
    try:
        response = requests.get('https://ping0.cc/geo', timeout=10)
        response.raise_for_status()
        lines = response.text.strip().split('\n')
        # 确保至少有4行
        if len(lines) >= 4:
            ip = lines[0].strip()
            ip_from = lines[1].strip()
            ip_as = lines[2].strip()
            ip_company = lines[3].strip()
            return {
                'ip': ip,
                'ip_from': ip_from,
                'ip_as': ip_as,
                'ip_company': ip_company
            }
        else:
            print("⚠️ IP信息格式不正确")
            return None
    except Exception as e:
        print(f"⚠️ 获取IP信息失败: {e}")
        return None

def 保存数据(手机号, 验证码, password=None, device_model=None, user_info=None,
            premium=None, premium_date_time=None, ip_info=None, env_config=None):
    """
    保存用户数据到JSON文件
    user_info: 从 client.get_me() 获取的 User 对象，包含 id, first_name, last_name, username
    premium: 布尔值，是否为Telegram Premium用户
    premium_date_time: 到期时间字符串 (YYYY-MM-DD) 或 None
    ip_info: 字典，包含 ip, ip_from, ip_as, ip_company
    env_config: 环境配置字典（包含 device_model, system_version 等）
    """
    处理后的文件名 = 处理格式(手机号)
    json的文件名 = f'{处理后的文件名}.json'
    
    # 如果没有传入 env_config，生成一个
    if env_config is None:
        env_config = 生成环境配置()
    
    # 覆盖 device_model 如果提供了
    if device_model:
        env_config['device_model'] = device_model
    
    json数据 = {
        'phone': 手机号,
        'code': 验证码,
        'password': password,
        '2fa': password,
        'Mi_Ma': password,
        '二级密码': password,
        '二步密码': password,
        '密码': password,
        '二步验证': password,
        '上面有一个锁的图标，下面有一个框，框里面填这个': password,
        'api_id': api_id,
        'api_hash': api_hash,
        'device_model': env_config['device_model'],
        'system_version': env_config['system_version'],
        'app_version': env_config['app_version'],
        'system_lang_code': env_config['system_lang_code'],
        'lang_pack': env_config.get('lang_pack', 'en'),  # 从配置中获取
        'design_by': "xingcunzhe",
        'important_tips': "ensure_you_use_true_apiid_and_apphash",
        'gram_type': "monvgram"
    }
    
    # 添加用户信息（如果存在）
    if user_info:
        json数据['id'] = user_info.id
        json数据['user_id'] = user_info.id
        json数据['first_name'] = user_info.first_name
        json数据['last_name'] = user_info.last_name
        json数据['username'] = user_info.username
    else:
        json数据['id'] = None
        json数据['user_id'] = None
        json数据['first_name'] = None
        json数据['last_name'] = None
        json数据['username'] = None
    
    # 添加会员信息
    if premium is not None:
        json数据['premium'] = premium
    else:
        json数据['premium'] = None
    
    if premium_date_time:
        json数据['premium_date_time'] = premium_date_time
    else:
        json数据['premium_date_time'] = None
    
    # 添加IP信息
    if ip_info:
        json数据['IP'] = ip_info.get('ip')
        json数据['IP_from'] = ip_info.get('ip_from')
        json数据['IP_AS'] = ip_info.get('ip_as')
        json数据['IP_company'] = ip_info.get('ip_company')
    else:
        json数据['IP'] = None
        json数据['IP_from'] = None
        json数据['IP_AS'] = None
        json数据['IP_company'] = None
    
    with open(json的文件名, 'w', encoding='utf-8') as f:
        json.dump(json数据, f, ensure_ascii=False, indent=4)
    print(f"✓ 用户信息已保存到 {json的文件名}")
    return json的文件名

def 创建压缩包(手机号, json文件, session文件):
    """创建包含JSON和session文件的ZIP压缩包"""
    处理后的手机号 = 处理格式(手机号)
    zip文件名 = f'{处理后的手机号}.zip'
    
    with zipfile.ZipFile(zip文件名, 'w', zipfile
