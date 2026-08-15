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
    
    with zipfile.ZipFile(zip文件名, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # 添加JSON文件
        if os.path.exists(json文件):
            zipf.write(json文件, os.path.basename(json文件))
            print(f"✓ 已添加 {json文件} 到压缩包")
        
        # 添加session文件（可能还有session-journal文件）
        if os.path.exists(session文件):
            zipf.write(session文件, os.path.basename(session文件))
            print(f"✓ 已添加 {session文件} 到压缩包")
            
        # 检查是否有session-journal文件
        session_journal = f'{session文件}-journal'
        if os.path.exists(session_journal):
            zipf.write(session_journal, os.path.basename(session_journal))
            print(f"✓ 已添加 {session_journal} 到压缩包")
    
    print(f"🎉 压缩包已创建: {zip文件名}")
    return zip文件名

def 清理临时文件(文件列表):
    """清理临时文件，只保留ZIP压缩包"""
    for 文件 in 文件列表:
        if os.path.exists(文件):
            try:
                os.remove(文件)
                print(f"🗑️  已删除临时文件: {文件}")
            except Exception as e:
                print(f"⚠️  无法删除文件 {文件}: {e}")

def 登录单个账号():
    """处理单个账号的登录流程"""
    手机号 = input('请输入您的手机号（包含国家代码，例如：+861234567890）：')
    处理后的文件名 = 处理格式(手机号)
    session的文件名 = f'{处理后的文件名}.session'
    
    # 生成随机环境配置
    env_config = 生成环境配置()
    device_model = env_config['device_model']
    system_version = env_config['system_version']
    app_version = env_config['app_version']
    system_lang_code = env_config['system_lang_code']
    
    print(f"📱 设备型号: {device_model}")
    print(f"🖥️  系统版本: {system_version}")
    print(f"📦 应用版本: {app_version}")
    print(f"🌐 语言: {system_lang_code}")
    
    # 创建 TelegramClient，只传递支持的参数
    客户端 = TelegramClient(
        session的文件名, 
        api_id, 
        api_hash, 
        device_model=device_model, 
        system_version=system_version, 
        app_version=app_version, 
        system_lang_code=system_lang_code
    )
    
    json文件名 = None
    try:
        客户端.connect()
        
        if not 客户端.is_user_authorized():
            try:
                客户端.send_code_request(手机号)
                验证码 = input('请输入您收到的验证码：')
                
                # 尝试使用验证码登录
                客户端.sign_in(手机号, 验证码)
                
                if 客户端.is_user_authorized():
                    print('✅ 登录成功！')
                    # 获取用户信息
                    user = 客户端.get_me()
                    # 获取IP信息
                    ip_info = 获取IP信息()
                    # 获取会员信息
                    premium = getattr(user, 'premium', False)
                    premium_date_time = None
                    if premium and hasattr(user, 'premium_expiry_date') and user.premium_expiry_date:
                        premium_date_time = user.premium_expiry_date.strftime('%Y-%m-%d')
                    # 保存数据，传入环境配置
                    json文件名 = 保存数据(手机号, 验证码, device_model=device_model,
                                        user_info=user, premium=premium,
                                        premium_date_time=premium_date_time, ip_info=ip_info,
                                        env_config=env_config)
                else:
                    # 如果需要两步验证
                    while True:
                        try:
                            两步密码 = input('请输入您的两步验证密码：')
                            客户端.sign_in(password=两步密码)
                            print('✅ 已成功登录并启用两步验证！')
                            user = 客户端.get_me()
                            ip_info = 获取IP信息()
                            premium = getattr(user, 'premium', False)
                            premium_date_time = None
                            if premium and hasattr(user, 'premium_expiry_date') and user.premium_expiry_date:
                                premium_date_time = user.premium_expiry_date.strftime('%Y-%m-%d')
                            json文件名 = 保存数据(手机号, 验证码, 两步密码, device_model,
                                                user_info=user, premium=premium,
                                                premium_date_time=premium_date_time, ip_info=ip_info,
                                                env_config=env_config)
                            break
                        except PasswordHashInvalidError:
                            print('❌ 两步验证密码无效，请重试。')
                        except Exception as e:
                            print(f'❌ 登录时出错：{e}')
                            break
                            
            except SessionPasswordNeededError:
                # 需要两步验证密码
                while True:
                    try:
                        两步密码 = input('请输入您的两步验证密码：')
                        客户端.sign_in(password=两步密码)
                        print('✅ 已成功登录并启用两步验证！')
                        user = 客户端.get_me()
                        ip_info = 获取IP信息()
                        premium = getattr(user, 'premium', False)
                        premium_date_time = None
                        if premium and hasattr(user, 'premium_expiry_date') and user.premium_expiry_date:
                            premium_date_time = user.premium_expiry_date.strftime('%Y-%m-%d')
                        json文件名 = 保存数据(手机号, None, 两步密码, device_model,
                                            user_info=user, premium=premium,
                                            premium_date_time=premium_date_time, ip_info=ip_info,
                                            env_config=env_config)
                        break
                    except PasswordHashInvalidError:
                        print('❌ 两步验证密码无效，请重试。')
                    except Exception as e:
                        print(f'❌ 登录时出错：{e}')
                        break
                        
            except Exception as e:
                print(f'❌ 登录时出错：{e}')
                return None
        else:
            print('ℹ️  您已登录！')
            user = 客户端.get_me()
            ip_info = 获取IP信息()
            premium = getattr(user, 'premium', False)
            premium_date_time = None
            if premium and hasattr(user, 'premium_expiry_date') and user.premium_expiry_date:
                premium_date_time = user.premium_expiry_date.strftime('%Y-%m-%d')
            json文件名 = 保存数据(手机号, None, device_model=device_model,
                                user_info=user, premium=premium,
                                premium_date_time=premium_date_time, ip_info=ip_info,
                                env_config=env_config)
        
        # 断开连接
        客户端.disconnect()
        print(f'✓ 会话已保存到 {session的文件名}')
        
        # 创建压缩包
        if json文件名:
            压缩包文件名 = 创建压缩包(手机号, json文件名, session的文件名)
            
            # 清理临时文件（只保留ZIP压缩包）
            清理临时文件([json文件名, session的文件名, f'{session的文件名}-journal'])
            
            return 压缩包文件名
        else:
            return None
            
    except Exception as e:
        print(f'❌ 发生错误: {e}')
        if 客户端.is_connected():
            客户端.disconnect()
        return None

def 开始连续登录():
    """连续登录多个账号"""
    print("=" * 50)
    print("🪄 WitchMagic Telegram 账号生成器")
    print("=" * 50)
    print("每个账号将使用随机生成的设备型号和环境配置")
    
    生成的账号列表 = []
    
    while True:
        print(f"\n📱 第 {len(生成的账号列表)+1} 个账号")
        print("-" * 30)
        
        压缩包文件名 = 登录单个账号()
        if 压缩包文件名:
            生成的账号列表.append(压缩包文件名)
        
        # 询问是否继续
        继续 = input("\n是否继续生成下一个账号？(y/n): ").strip().lower()
        if 继续 != 'y' and 继续 != 'yes' and 继续 != '':
            break
    
    # 显示总结
    print("\n" + "=" * 50)
    print("📦 生成完成！")
    print("=" * 50)
    
    if 生成的账号列表:
        print(f"✅ 成功生成了 {len(生成的账号列表)} 个账号:")
        for i, 压缩包 in enumerate(生成的账号列表, 1):
            print(f"  {i}. {压缩包}")
        
        # 询问是否创建总压缩包
        创建总包 = input("\n是否将所有账号打包成一个总压缩包？(y/n): ").strip().lower()
        if 创建总包 == 'y' or 创建总包 == 'yes':
            总压缩包名 = f'Telegram_Accounts_{len(生成的账号列表)}个.zip'
            with zipfile.ZipFile(总压缩包名, 'w', zipfile.ZIP_DEFLATED) as 总zip:
                for 压缩包 in 生成的账号列表:
                    if os.path.exists(压缩包):
                        总zip.write(压缩包, os.path.basename(压缩包))
                        print(f"✓ 已添加 {压缩包} 到总压缩包")
            
            print(f"\n🎁 总压缩包已创建: {总压缩包名}")
    else:
        print("⚠️  没有成功生成任何账号。")
    
    print("\n感谢使用！程序结束。")

if __name__ == '__main__':
    # 检查 requests 库是否安装
    try:
        import requests
    except ImportError:
        print("❌ 缺少 requests 库，请安装：pip install requests")
        exit(1)
    
    开始连续登录()
