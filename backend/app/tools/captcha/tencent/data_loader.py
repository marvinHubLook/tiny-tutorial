from DrissionPage import ChromiumPage
import json
import time
import os

current_project_path = '/home/bingo/PycharmProjects/tiny-tutorial/backend'
image_base_path = os.path.join(current_project_path,"app","images","captcha","tencent/")


def get_captcha_json():
    """
    通过 ChromiumPage 获取验证码图片，使用 cap_union_new_getsig 事件
    1. 打开目标网页
    2. 等待页面加载，确保元素可点击
    3. 等待iframe内容加载完成
    4. 等待reload按钮出现
    5. 点击reload按钮，等待验证码图片加载完成
    6. 获取验证码图片
    7. 保存验证码图片到本地
    8. 关闭页面

    :return: None
    """
    page = ChromiumPage()
    try:
        # 打开目标网页
        page.get('https://cloud.tencent.com/product/captcha')

        # 增加等待时间，确保页面完全加载
        time.sleep(3)

        # 等待页面加载，确保元素可点击
        page.wait.ele_displayed('xpath=//a[@id="vtt_click"]', timeout=30)
        vtt_button = page('#vtt_click')
        if vtt_button:

            vtt_button.click()
            # 点击后等待一下
            time.sleep(2)
        else:
            print("未找到 id='vtt_click' 的元素")
            return None

        # 增加iframe等待时间和重试机制
        iframe = None
        max_retries = 5
        for retry in range(max_retries):
            try:
                iframe = page.get_frame('xpath=//iframe[@id="tcaptcha_iframe"]', timeout=10)
                if iframe:
                    print(f"成功获取iframe: {iframe}")
                    break
            except Exception as e:
                print(f"第{retry + 1}次获取iframe失败: {e}")
                time.sleep(2)

        if not iframe:
            print("无法获取iframe")
            return None

        # 等待iframe内容加载完成
        time.sleep(3)
        # 等待reload按钮出现，增加超时时间
        try:
            iframe.wait.ele_displayed('xpath=//a[@id="reload"]', timeout=20)
        except Exception as e:
            print(f"等待reload按钮失败: {e}")
            # 尝试等待页面稳定
            time.sleep(5)

        reload_button = iframe('#reload')
        if reload_button:
            iframe.listen.start(targets=["cap_union_new_getsig"])
            for i in range(100):
                print(f"第{i + 1}次尝试")
                try:
                    # 在点击前检查元素是否仍然可用
                    if not reload_button.states.is_alive:
                        print("reload按钮不再可用，重新查找")
                        reload_button = iframe('#reload')
                        if not reload_button:
                            print("无法重新找到reload按钮")
                            break

                    reload_button.click()

                    # 等待网络请求
                    for packet in iframe.listen.steps(timeout=30):
                        print(f"url : {packet.url}")
                        response = packet.response
                        if "cap_union_new_getsig" in packet.url:
                            response_body = response.body
                            print(f"json_data: {response_body}")
                            # sleep 2s
                            time.sleep(2)
                            # 获取验证码图片
                            try:
                                img_element = iframe.ele("xpath=//img[@id='tcaptcha-img']")
                                if img_element:
                                    img_url = img_element.attr('src')
                                    response = iframe.session.get(img_url)
                                    img_data = None
                                    if response.status_code == 200:
                                        img_data = response.content
                                        word = response_body["vttword"]
                                        with open(f"{image_base_path}{160+i}.{word}.jpg", "wb") as f:
                                            f.write(img_data)
                                        iframe.get_screenshot(f"{image_base_path}{160+i}.{word}.png")
                                    print(f"验证码图片数据: {img_data} , img_url: {img_url}, word: {word}")
                                else:
                                    print("未找到验证码图片")
                            except Exception as img_e:
                                print(f"获取验证码图片失败: {img_e}")
                            break
                    # 每次尝试之间增加等待时间
                    time.sleep(2)

                except Exception as click_e:
                    print(f"点击reload按钮失败: {click_e}")
                    # 如果点击失败，等待页面稳定后重试
                    time.sleep(5)
        else:
            print("未找到 id='reload' 的元素")

    except Exception as e:
        print(f"发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # 关闭页面
        page.quit()
def get_captcha_json_with_retry():
    """带重试机制的版本"""
    max_attempts = 3
    for attempt in range(max_attempts):
        print(f"尝试第 {attempt + 1} 次获取验证码")
        try:
            result = get_captcha_json()
            if result:
                return result
        except Exception as e:
            print(f"第 {attempt + 1} 次尝试失败: {e}")

        if attempt < max_attempts - 1:
            print("等待后重试...")
            time.sleep(5)

    print("所有尝试都失败了")
    return None


if __name__ == "__main__":
    # 使用带重试机制的版本
    get_captcha_json_with_retry()