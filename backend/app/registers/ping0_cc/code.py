import re

import execjs
from bs4 import BeautifulSoup
from curl_cffi import requests
with open('./code.js','r',encoding='utf-8') as f:
    js = f.read()


def extract_ip_info(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')

    result = {}

    # 查找所有包含信息的行
    info_lines = soup.find_all('div', class_='line')

    for line in info_lines:
        name_div = line.find('div', class_='name')
        content_div = line.find('div', class_='content')

        if name_div and content_div:
            name = name_div.get_text(strip=True)
            content = content_div.get_text(strip=True)

            # 提取IP地址
            if 'IP 地址' in name:
                # 从内容中提取IP地址，去掉额外文本
                ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', content)
                if ip_match:
                    result['IP地址'] = ip_match.group(1)

            # 提取IP位置
            elif 'IP 位置' in name:
                # 去掉"错误提交"文本
                location = content.replace('错误提交', '').strip()
                result['IP位置'] = location

            # 提取ASN
            elif name == 'ASN':
                # 提取ASN编号
                asn_match = re.search(r'(AS\d+)', content)
                if asn_match:
                    result['ASN'] = asn_match.group(1)

            # 提取ASN所有者
            elif 'ASN 所有者' in name:
                # 去掉标签，提取公司名和域名
                # 先移除HTML标签
                content_clean = re.sub(r'IDC\s*', '', content)
                # 提取公司名（在" — "之前）
                if ' — ' in content_clean:
                    company_name = content_clean.split(' — ')[0].strip()
                    domain = content_clean.split(' — ')[1].strip()
                    result['ASN所有者'] = company_name
                    result['ASN所有者域名'] = domain
                else:
                    result['ASN所有者'] = content_clean.strip()

            # 提取企业
            elif name == '企业':
                content_clean = re.sub(r'IDC\s*', '', content)
                if ' — ' in content_clean:
                    company_name = content_clean.split(' — ')[0].strip()
                    domain = content_clean.split(' — ')[1].strip()
                    result['企业'] = company_name
                    result['企业域名'] = domain
                else:
                    result['企业'] = content_clean.strip()

            # 提取经度
            elif name == '经度':
                result['经度'] = content

            # 提取纬度
            elif name == '纬度':
                result['纬度'] = content

            # 提取IP类型
            elif 'IP类型' in name:
                # 查找label标签
                label = content_div.find('span', class_='label')
                if label:
                    result['IP类型'] = label.get_text(strip=True)

            # 提取风控值
            elif '风控值' in name:
                # 查找风控值百分比
                risk_match = re.search(r'(\d+%)', content)
                if risk_match:
                    result['风控值'] = risk_match.group(1)
                # 提取风险等级
                if '中性' in content:
                    result['风险等级'] = '中性'
                elif '纯净' in content:
                    result['风险等级'] = '纯净'
                elif '极度纯净' in content:
                    result['风险等级'] = '极度纯净'
                elif '轻微风险' in content:
                    result['风险等级'] = '轻微风险'
                elif '稍高风险' in content:
                    result['风险等级'] = '稍高风险'
                elif '极度风险' in content:
                    result['风险等级'] = '极度风险'

            # 提取原生IP
            elif '原生 IP' in name:
                label = content_div.find('span', class_='label')
                if label:
                    result['原生IP'] = label.get_text(strip=True)

    return result

def main():
    session = requests.Session(impersonate='chrome',proxy="http://192.168.1.100:7890")
    response = session.get('https://ping0.cc')
    x1 = re.search(r"window\.x1\s*=\s*'(.*?)'", response.text)
    if x1:
        x1 = x1.group(1)
        print(f"x1: {x1}")
    else:
        print(f"无法获取x1 {response.text}")
        return

    difficulty = re.search(r"window\.difficulty\s*=\s*'(.*?)'", response.text)
    if difficulty:
        difficulty = difficulty.group(1)
        print(f"difficulty: {difficulty}")
    else:
        print(f"无法获取difficulty {response.text}")
        return

    ctx = execjs.compile(js)
    result = ctx.call('code1', x1 , difficulty)
    js1key = result['js1key']
    _pow = result['pow']
    print(f"js1key: {js1key}", f"_pow: {_pow}")

    session.cookies.set('js1key', str(js1key))
    session.cookies.set('pow', str(_pow))

    response = session.get('https://ping0.cc')
    if '验证码' in response.text:
        print("触发滑块")
        return

    result = extract_ip_info(response.text)

if __name__ == '__main__':
    main()