import time
import pandas as pd
import os
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import re


class GuangzhouWeatherCrawler:
    def __init__(self, edge_driver_path):
        """初始化Edge浏览器驱动"""

        # 区域ID映射
        self.region_ids = {
            "广州": "59287",
            "番禺区": "60025",
            "海珠区": "72024",
            "黄埔区": "72027",
            "荔湾区": "72022",
            "天河区": "72025",
            "增城区": "60368",
            "白云区": "72026",
            "越秀区": "72023",
            "花都区": "60024",
            "从化区": "70077",
            "南沙区": "72028"
        }

        # 基础URL模板
        self.base_url = "https://tianqi.2345.com/wea_history/{id}.htm"

        # 存储所有数据
        self.all_data = []

        # 初始化Edge驱动
        self.init_edge_driver(edge_driver_path)

        self.wait = WebDriverWait(self.driver, 30)

    def init_edge_driver(self, driver_path):
        """初始化Edge驱动"""
        print(f"使用EdgeDriver路径: {driver_path}")

        # 检查驱动文件是否存在
        if not os.path.exists(driver_path):
            print(f"错误: EdgeDriver文件不存在: {driver_path}")
            print("请确保提供的路径正确，并且EdgeDriver已下载")
            sys.exit(1)

        try:
            # 配置Edge选项
            options = webdriver.EdgeOptions()

            # 防止被检测为自动化工具
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)

            # 添加用户代理
            options.add_argument(
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0')

            # 禁用一些可能影响性能的功能
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--no-sandbox')

            # 最大化窗口
            options.add_argument('--start-maximized')

            # 创建服务
            service = Service(driver_path)

            # 创建驱动
            self.driver = webdriver.Edge(service=service, options=options)

            # 设置页面加载超时时间
            self.driver.set_page_load_timeout(60)

            print("Edge驱动初始化成功!")

        except Exception as e:
            print(f"Edge驱动初始化失败: {e}")
            sys.exit(1)

    def get_region_url(self, region_name):
        """获取区域URL"""
        if region_name in self.region_ids:
            return self.base_url.format(id=self.region_ids[region_name])
        return None

    def extract_summary_stats(self):
        """提取汇总统计数据"""
        stats = {}
        try:
            # 获取所有li元素
            li_elements = self.driver.find_elements(By.CSS_SELECTOR, ".history-msg li")

            for li in li_elements:
                text = li.text.strip()
                if not text:
                    continue

                # 平均高温
                if '平均高温' in text:
                    match = re.search(r'(\d+)°', text)
                    if match:
                        stats['平均高温'] = match.group(1)

                # 平均低温
                elif '平均低温' in text:
                    match = re.search(r'(\d+)°', text)
                    if match:
                        stats['平均低温'] = match.group(1)

                # 极端高温
                elif '极端高温' in text:
                    temp_match = re.search(r'(\d+)°', text)
                    date_match = re.search(r'\((\d{4}-\d{2}-\d{2})\)', text)
                    temp = temp_match.group(1) if temp_match else ''
                    date = date_match.group(1) if date_match else ''
                    stats['极端高温'] = f"{temp} ({date})"

                # 极端低温
                elif '极端低温' in text:
                    temp_match = re.search(r'(\d+)°', text)
                    date_match = re.search(r'\((\d{4}-\d{2}-\d{2})\)', text)
                    temp = temp_match.group(1) if temp_match else ''
                    date = date_match.group(1) if date_match else ''
                    stats['极端低温'] = f"{temp} ({date})"

                # 平均空气质量指数
                elif '平均空气质量指数' in text:
                    match = re.search(r'(\d+)', text)
                    if match:
                        stats['平均空气质量指数'] = match.group(1)

                # 空气最好
                elif '空气最好' in text:
                    aqi_match = re.search(r'(\d+)\s*优', text)
                    date_match = re.search(r'\((\d{1,2}月\d{1,2}日)\)', text)
                    aqi = aqi_match.group(1) if aqi_match else ''
                    date = date_match.group(1) if date_match else ''
                    stats['空气最好'] = f"{aqi} ({date})"

                # 空气最差
                elif '空气最差' in text:
                    aqi_match = re.search(r'(\d+)\s*(轻度|良|优)', text)
                    date_match = re.search(r'\((\d{1,2}月\d{1,2}日)\)', text)
                    aqi = aqi_match.group(1) if aqi_match else ''
                    date = date_match.group(1) if date_match else ''
                    stats['空气最差'] = f"{aqi} ({date})"

        except Exception as e:
            print(f"提取汇总统计数据时出错: {e}")

        # 确保所有字段都有值
        for key in ['平均高温', '平均低温', '极端高温', '极端低温',
                    '平均空气质量指数', '空气最好', '空气最差']:
            if key not in stats:
                stats[key] = ""

        return stats

    def extract_table_data(self, region_name):
        """提取表格数据"""
        table_data = []

        try:
            # 尝试不同的表格选择器
            table_selectors = [
                "table.history-table",
                "table",
                ".box-mod-tb table",
                "tbody table"
            ]

            table = None
            for selector in table_selectors:
                try:
                    tables = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for t in tables:
                        if t.is_displayed():
                            table = t
                            break
                    if table:
                        break
                except:
                    continue

            if not table:
                print("无法找到表格，尝试查找任何表格")
                tables = self.driver.find_elements(By.TAG_NAME, "table")
                if tables:
                    table = tables[0]

            if not table:
                print("页面中没有找到任何表格")
                return table_data

            # 获取所有行
            rows = table.find_elements(By.TAG_NAME, "tr")

            if len(rows) <= 1:
                print(f"表格只有 {len(rows)} 行，可能没有数据")
                return table_data

            for i, row in enumerate(rows):
                # 跳过表头
                if i == 0:
                    continue

                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) >= 6:
                    # 提取日期
                    date_text = cols[0].text.strip()

                    # 尝试从日期文本中提取YYYY-MM-DD格式
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_text)
                    if date_match:
                        date = date_match.group(1)
                    else:
                        # 如果没有匹配，尝试其他格式
                        date = date_text.split()[0] if date_text else ""

                    # 提取最高温
                    high_temp = cols[1].text.strip()
                    high_temp = re.sub(r'[^\d.-]', '', high_temp)  # 只保留数字和小数点

                    # 提取最低温
                    low_temp = cols[2].text.strip()
                    low_temp = re.sub(r'[^\d.-]', '', low_temp)  # 只保留数字和小数点

                    # 提取天气
                    weather = cols[3].text.strip()

                    # 提取风力风向
                    wind = cols[4].text.strip()

                    # 提取空气质量指数
                    aqi_text = cols[5].text.strip()
                    aqi_match = re.search(r'(\d+)', aqi_text)
                    aqi = aqi_match.group(1) if aqi_match else aqi_text

                    table_data.append({
                        '区域': region_name,
                        '日期': date,
                        '最高温': high_temp,
                        '最低温': low_temp,
                        '天气': weather,
                        '风力风向': wind,
                        '空气质量指数': aqi
                    })

        except Exception as e:
            print(f"提取表格数据时出错: {e}")
            # 打印页面标题和URL以便调试
            print(f"当前页面标题: {self.driver.title}")
            print(f"当前页面URL: {self.driver.current_url}")

        return table_data

    def click_previous_month(self):
        """点击上一月按钮"""
        try:
            # 查找上一月按钮
            prev_button_selectors = [
                "#js_prevMonth",
                "a[onclick*='上一月']",
                "a:contains('上一月')"
            ]

            for selector in prev_button_selectors:
                try:
                    prev_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if prev_button.is_displayed() and prev_button.is_enabled():
                        # 滚动到按钮位置
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", prev_button)
                        time.sleep(0.5)

                        # 点击按钮
                        prev_button.click()

                        # 等待页面加载
                        time.sleep(2)
                        return True
                except:
                    continue

            print("找不到上一月按钮")
            return False

        except Exception as e:
            print(f"点击上一月按钮时出错: {e}")
            return False

    def click_next_month(self):
        """点击下一月按钮"""
        try:
            # 查找下一月按钮
            next_button_selectors = [
                "#js_nextMonth",
                "a[onclick*='下一月']",
                "a:contains('下一月')"
            ]

            for selector in next_button_selectors:
                try:
                    next_button = self.driver.find_element(By.CSS_SELECTOR, selector)

                    # 检查按钮是否可用（没有no-data-btn类）
                    class_name = next_button.get_attribute("class") or ""
                    if "no-data-btn" in class_name:
                        print("下一月按钮不可用（有no-data-btn类）")
                        return False

                    if next_button.is_displayed() and next_button.is_enabled():
                        # 滚动到按钮位置
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                        time.sleep(0.5)

                        # 点击按钮
                        next_button.click()

                        # 等待页面加载
                        time.sleep(2)
                        return True
                except:
                    continue

            print("找不到下一月按钮")
            return False

        except Exception as e:
            print(f"点击下一月按钮时出错: {e}")
            return False

    def crawl_region(self, region_name):
        """爬取单个区域的所有月份数据"""
        print(f"\n开始爬取 {region_name} 的数据...")

        # 获取区域URL
        url = self.get_region_url(region_name)
        if not url:
            print(f"无法获取 {region_name} 的URL")
            return

        print(f"访问URL: {url}")

        # 打开区域页面
        try:
            self.driver.get(url)
            print("页面加载中，请等待...")
            time.sleep(5)

        except Exception as e:
            print(f"访问页面失败: {e}")
            return

        # 第一步：点击上一月按钮23次，回到2024年1月
        print("点击上一月按钮23次，回到2024年1月...")
        for i in range(23):
            print(f"点击第 {i + 1} 次上一月按钮...")
            if not self.click_previous_month():
                print(f"第 {i + 1} 次点击失败，可能已到达最早月份")
                break
            time.sleep(1)

        print("开始爬取数据...")

        # 记录已爬取的页面数
        pages_crawled = 0

        # 第二步：开始爬取数据，每页爬完后点击下一页
        while True:
            pages_crawled += 1
            print(f"\n爬取第 {pages_crawled} 页数据...")

            # 提取汇总统计数据
            summary_stats = self.extract_summary_stats()

            # 提取表格数据
            table_data = self.extract_table_data(region_name)

            if table_data:
                # 合并汇总统计数据到表格数据
                for record in table_data:
                    record.update(summary_stats)

                # 添加到总数据
                self.all_data.extend(table_data)

                print(f"成功提取 {len(table_data)} 条记录")

                # 打印第一行数据作为示例
                if len(table_data) > 0:
                    print(f"示例数据: {table_data[0]}")
            else:
                print("警告: 未提取到表格数据")

                # 保存页面截图以便调试
                try:
                    screenshot_path = f"screenshot_{region_name}_page{pages_crawled}.png"
                    self.driver.save_screenshot(screenshot_path)
                    print(f"已保存页面截图到 {screenshot_path}")
                except:
                    pass

            # 尝试点击下一页按钮
            print("尝试点击下一页按钮...")
            if not self.click_next_month():
                print("下一页按钮不可用，可能已到达最后一页")
                break

            # 检查是否爬取足够多的页面（最多24页，从2024年1月到2025年12月）
            if pages_crawled >= 24:
                print(f"已爬取 {pages_crawled} 页，达到最大页数限制")
                break

        print(
            f"完成爬取 {region_name}，共爬取 {pages_crawled} 页，{len([d for d in self.all_data if d['区域'] == region_name])} 条记录")

    def crawl_all_regions(self):
        """爬取所有区域"""
        for i, region_name in enumerate(self.region_ids.keys()):
            print(f"\n{'=' * 60}")
            print(f"进度: {i + 1}/{len(self.region_ids)} - {region_name}")
            print(f"{'=' * 60}")

            self.crawl_region(region_name)

            # 区域间延迟
            if i < len(self.region_ids) - 1:
                print(f"等待5秒后爬取下一个区域...")
                time.sleep(5)

    def save_to_csv(self, filename='广州天气数据.csv'):
        """保存数据到CSV文件"""
        if not self.all_data:
            print("没有数据可保存")
            return

        try:
            df = pd.DataFrame(self.all_data)

            # 重新排列列的顺序
            columns_order = ['区域', '日期', '最高温', '最低温', '天气', '风力风向', '空气质量指数',
                             '平均高温', '平均低温', '极端高温', '极端低温', '平均空气质量指数',
                             '空气最好', '空气最差']

            # 只保留存在的列
            existing_columns = [col for col in columns_order if col in df.columns]
            df = df[existing_columns]

            # 按区域和日期排序
            try:
                # 先尝试将日期转换为datetime格式
                df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
                df = df.sort_values(['区域', '日期'])
                df['日期'] = df['日期'].dt.strftime('%Y-%m-%d')
            except Exception as e:
                print(f"日期格式化失败: {e}，按原始顺序保存")
                # 按区域和原始顺序排序
                df = df.sort_values(['区域'])

            df.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"\n数据已保存到 {filename}")
            print(f"共保存 {len(df)} 条记录")

            # 显示统计信息
            print(f"\n数据统计:")
            print(f"总记录数: {len(df)}")
            print(f"区域数量: {df['区域'].nunique()}")

            if '日期' in df.columns:
                # 找到有效的日期
                valid_dates = df[df['日期'].notna() & (df['日期'] != '')]['日期']
                if len(valid_dates) > 0:
                    print(f"日期范围: {valid_dates.min()} 到 {valid_dates.max()}")

            # 按区域统计
            region_counts = df['区域'].value_counts()
            print("\n各区域记录数:")
            for region, count in region_counts.items():
                print(f"  {region}: {count} 条")

            # 保存汇总文件
            self.save_summary_file(df)

            return df

        except Exception as e:
            print(f"保存数据时出错: {e}")
            # 尝试保存为简单格式
            try:
                simple_df = pd.DataFrame(self.all_data)
                backup_filename = f'广州天气数据_备份_{time.strftime("%Y%m%d_%H%M%S")}.csv'
                simple_df.to_csv(backup_filename, index=False, encoding='utf-8-sig')
                print(f"已保存备份数据到 {backup_filename}")
                return simple_df
            except:
                print("无法保存数据")
                return None

    def save_summary_file(self, df):
        """保存汇总统计文件"""
        try:
            # 创建区域汇总
            regions = df['区域'].unique()
            summary_data = []

            for region in regions:
                region_df = df[df['区域'] == region]
                if len(region_df) > 0:
                    # 对于每个区域，我们可能需要从多条记录中提取不同的汇总信息
                    # 这里我们取第一条记录中的汇总数据
                    first_record = region_df.iloc[0]

                    summary = {
                        '区域': region,
                        '平均高温': first_record.get('平均高温', ''),
                        '平均低温': first_record.get('平均低温', ''),
                        '极端高温': first_record.get('极端高温', ''),
                        '极端低温': first_record.get('极端低温', ''),
                        '平均空气质量指数': first_record.get('平均空气质量指数', ''),
                        '空气最好': first_record.get('空气最好', ''),
                        '空气最差': first_record.get('空气最差', ''),
                        '记录数': len(region_df)
                    }
                    summary_data.append(summary)

            summary_df = pd.DataFrame(summary_data)
            summary_filename = f'广州天气汇总_{time.strftime("%Y%m%d_%H%M%S")}.csv'
            summary_df.to_csv(summary_filename, index=False, encoding='utf-8-sig')
            print(f"汇总统计数据已保存到 {summary_filename}")

        except Exception as e:
            print(f"保存汇总文件时出错: {e}")

    def close(self):
        """关闭浏览器"""
        try:
            self.driver.quit()
            print("浏览器已关闭")
        except:
            pass

    def run(self):
        """运行爬虫"""
        try:
            print("开始爬取广州天气数据...")
            print("注意：这可能需要一些时间，请耐心等待...")
            print("流程说明：")
            print("1. 每个区域从当前页面开始")
            print("2. 点击'上一月'按钮23次，回到2024年1月")
            print("3. 从2024年1月开始爬取，每页爬完后点击'下一页'")
            print("4. 直到'下一页'按钮不可用或达到24页为止")

            self.crawl_all_regions()

            if self.all_data:
                self.save_to_csv()
            else:
                print("未爬取到任何数据")

        except KeyboardInterrupt:
            print("\n用户中断程序")
            if self.all_data:
                print("正在保存已爬取的数据...")
                self.save_to_csv('广州天气数据_部分.csv')
        except Exception as e:
            print(f"爬取过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            if self.all_data:
                print("正在保存已爬取的数据...")
                self.save_to_csv('广州天气数据_异常保存.csv')
        finally:
            self.close()


# 主程序
if __name__ == "__main__":
    # 使用您提供的最新EdgeDriver路径
    edge_driver_path = r"D:\download\edgedriver_win64\msedgedriver.exe"

    # 检查路径是否存在
    if not os.path.exists(edge_driver_path):
        print(f"错误: EdgeDriver文件不存在: {edge_driver_path}")
        print("请检查路径是否正确")
        sys.exit(1)

    # 运行爬虫
    crawler = GuangzhouWeatherCrawler(edge_driver_path)
    crawler.run()

    print("\n程序结束!")