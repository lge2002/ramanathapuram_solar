from django.core.management.base import BaseCommand
from django.conf import settings
from weather.models import ramanadhapuram_forecast
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
from datetime import datetime, timedelta
import time
import os
import cv2
import numpy as np
import pytz
import json
import requests

class Command(BaseCommand):
    help = 'Automates screenshot capture from Windy.com, crops, analyzes ramanadhapuram_forecast levels, and stores data.'

    BLUE_DOT_XPATH = '//*[@id="leaflet-map"]/div[1]/div[4]/div[2]'
    VISIBLE_LAYER = '/html/body/span[1]/div/div[1]/div[6]/div[1]/div[2]'
    DRAGGABLE_ELEMENT_XPATH = "//*[@id='radar-bar']/div[3]"
    X_OFFSET_FOR_DRAG = 35
    Y_OFFSET = 0

    CROP_BOX_TN_REGION = (760, 180, 920, 440)

    API_ENDPOINT_URL = "http://172.16.7.118:8003/api/tamilnadu/satellite/push.windy_radar_data.php?type=adhani_solar"

    def _round_to_nearest_minutes(self, dt_object, minutes=15):
        total_minutes = dt_object.hour * 60 + dt_object.minute + dt_object.second / 60.0
        rounded_total_minutes = round(total_minutes / minutes) * minutes
        diff_minutes = rounded_total_minutes - total_minutes
        rounded_dt = dt_object + timedelta(minutes=diff_minutes)
        rounded_dt = rounded_dt.replace(second=0, microsecond=0)
        return rounded_dt

    def _get_image_analysis_directories(self, timestamp_str):
        base_image_dir = os.path.join(settings.BASE_DIR, "images", timestamp_str)
        full_screenshots_dir = os.path.join(base_image_dir, "full_screenshots")
        drag_images_dir = os.path.join(base_image_dir, "drag_images")
        analyzed_crops_dir = os.path.join(base_image_dir, "analyzed_crops")

        os.makedirs(full_screenshots_dir, exist_ok=True)
        os.makedirs(drag_images_dir, exist_ok=True)
        os.makedirs(analyzed_crops_dir, exist_ok=True)
        return full_screenshots_dir, drag_images_dir, analyzed_crops_dir

    def _automate_screenshot_capture(self, driver, wait, timestamp_str, full_screenshots_dir, drag_images_dir, analyzed_crops_dir):
        full_screenshot_path_before_drag = os.path.join(full_screenshots_dir, f"windy_map_full_before_drag_{timestamp_str}.png")
        cropped_image_path = os.path.join(analyzed_crops_dir, f"windy_map_cropped_{timestamp_str}.png")
        full_screenshot_path_after_drag = os.path.join(drag_images_dir, f"windy_map_full_after_drag_{timestamp_str}.png")

        try:
            driver.get("https://www.windy.com/-Satellite-satellite?satellite,9.237,78.372,11,p:favs")
            self.stdout.write("Navigated to Windy.com with satellite layer active.")

            try:
                self.stdout.write('Attempting to dismiss cookie consent...')
                cookie_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.cc-dismiss, a[aria-label="dismiss cookie message"]')))
                cookie_button.click()
                self.stdout.write('Cookie consent dismissed.')
                time.sleep(1)
            except Exception:
                self.stdout.write("No cookie message found or already dismissed. Continuing...")

            self.stdout.write("Waiting for map to fully load and stabilize (8 seconds)...")
            time.sleep(8)

            try:
                self.stdout.write("Attempting to click the 'Visible' layer toggle...")
                visible_layer_button = wait.until(EC.element_to_be_clickable((By.XPATH, self.VISIBLE_LAYER)))
                visible_layer_button.click()
                self.stdout.write("Successfully clicked the 'Visible' layer toggle.")
                time.sleep(5)
            except Exception as e:
                self.stderr.write(self.style.WARNING(f"Warning: Visibility toggle failed: {e}. Ensure VISIBLE_LAYER XPath is correct."))

            try:
                dot_element = wait.until(EC.presence_of_element_located((By.XPATH, self.BLUE_DOT_XPATH)))
                driver.execute_script("arguments[0].style.display = 'none';", dot_element)
                self.stdout.write("Attempted to hide blue dot via JavaScript.")
                time.sleep(1)
            except Exception:
                self.stdout.write("Blue dot not found or couldn't hide via JS. Trying ESC key as fallback...")
                try:
                    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    self.stdout.write("Pressed ESC key to dismiss elements.")
                    time.sleep(1)
                except Exception as esc_e:
                    self.stdout.write(f"Failed to press ESC key: {esc_e}. Blue dot might still be visible.")

            time.sleep(2)

            self.stdout.write(f"Saving full screenshot BEFORE drag to {full_screenshot_path_before_drag}")
            driver.save_screenshot(full_screenshot_path_before_drag)

            self.stdout.write("Attempting to perform drag action on the time slider...")
            try:
                draggable_element = wait.until(EC.presence_of_element_located((By.XPATH, self.DRAGGABLE_ELEMENT_XPATH)))
                actions = ActionChains(driver)
                actions.drag_and_drop_by_offset(draggable_element, self.X_OFFSET_FOR_DRAG, self.Y_OFFSET).perform()
                self.stdout.write(f"Drag action performed by offset ({self.X_OFFSET_FOR_DRAG}, {self.Y_OFFSET}).")
                time.sleep(3)
                self.stdout.write(f"Saving full screenshot AFTER drag to {full_screenshot_path_after_drag}")
                driver.save_screenshot(full_screenshot_path_after_drag)
                self.stdout.write(f"Screenshot after drag saved at: {full_screenshot_path_after_drag}")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error during drag operation: {e}. Please ensure DRAGGABLE_ELEMENT_XPATH is correct and element is interactive."))
                full_screenshot_path_after_drag = None

            try:
                if not full_screenshot_path_after_drag or not os.path.exists(full_screenshot_path_after_drag):
                    raise FileNotFoundError(f"Screenshot AFTER drag not found at {full_screenshot_path_after_drag}")
                full_img = Image.open(full_screenshot_path_after_drag)
                if not (0 <= self.CROP_BOX_TN_REGION[0] < self.CROP_BOX_TN_REGION[2] <= full_img.width and
                        0 <= self.CROP_BOX_TN_REGION[1] < self.CROP_BOX_TN_REGION[3] <= full_img.height):
                    self.stderr.write(self.style.ERROR(f"Crop box {self.CROP_BOX_TN_REGION} out of bounds for image size {full_img.size}! Skipping crop."))
                    cropped_image_path = None
                else:
                    cropped_img = full_img.crop(self.CROP_BOX_TN_REGION)
                    cropped_img.save(cropped_image_path)
                    self.stdout.write(f"Cropped Tamil Nadu image saved at: {cropped_image_path}")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error during image cropping from AFTER drag: {e}"))
                cropped_image_path = None

            return full_screenshot_path_before_drag, cropped_image_path, full_screenshot_path_after_drag

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred during browser automation: {e}"))
            return None, None, None

    def _analyze_cloud_percentage(self, image_path):
        if not image_path or not os.path.exists(image_path):
            self.stderr.write(self.style.ERROR(f"Image for analysis not found or path is invalid: {image_path}"))
            return None
        try:
            img = cv2.imread(image_path)
            if img is None:
                self.stderr.write(self.style.ERROR(f"Could not read image with OpenCV (might be corrupted or not an image): {image_path}"))
                return None
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

            # Define multiple cloud-like HSV ranges
            lower_white = np.array([0, 0, 190])
            upper_white = np.array([180, 60, 255])

            lower_gray = np.array([0, 0, 120])
            upper_gray = np.array([180, 50, 200])

            lower_brown = np.array([5, 50, 100])
            upper_brown = np.array([25, 200, 200])

            lower_blue = np.array([90, 15, 90])
            upper_blue = np.array([130, 90, 255])

            # Create masks for each range
            mask_white = cv2.inRange(hsv, lower_white, upper_white)
            mask_gray = cv2.inRange(hsv, lower_gray, upper_gray)
            mask_brown = cv2.inRange(hsv, lower_brown, upper_brown)
            mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)

            # Combine masks
            final_mask = cv2.bitwise_or(mask_white, mask_gray)
            final_mask = cv2.bitwise_or(final_mask, mask_brown)
            final_mask = cv2.bitwise_or(final_mask, mask_blue)

            # Calculate coverage
            total_pixels = img.shape[0] * img.shape[1]
            cloudy_pixels = cv2.countNonZero(final_mask)
            cloud_percentage = (cloudy_pixels / total_pixels) * 100 if total_pixels > 0 else 0.0

            # Optional: Save debug mask
            # debug_path = image_path.replace(".png", "_cloudmask_debug.png")
            # cv2.imwrite(debug_path, final_mask)
            # self.stdout.write(self.style.WARNING(f"Debug cloud mask saved at: {debug_path}"))

            self.stdout.write(self.style.SUCCESS(f"Analyzed {os.path.basename(image_path)}: {cloud_percentage:.2f}% cloud coverage."))
            return cloud_percentage

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error during image analysis for {image_path}: {e}"))
            return None


    def _store_data_to_db(self, timestamp, location_name, cloud_percentage, full_screenshot_path, drag_image_path):
        try:
            if settings.USE_TZ and timestamp.tzinfo is None:
                target_tz = pytz.timezone(settings.TIME_ZONE)
                timestamp = target_tz.localize(timestamp)

            ramanadhapuram_forecast.objects.update_or_create(
                timestamp=timestamp,
                city=location_name,
                defaults={
                    'values': f"{cloud_percentage:.2f}%",
                    'type': "adhani_solar",
                }
            )
            self.stdout.write(self.style.SUCCESS(f"Cloud data for {location_name} at {timestamp.strftime('%Y-%m-%d %H:%M:%S')} saved to database."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error saving data to Django model: {e}"))

    # --- NEW METHOD TO PUSH DATA TO URL ---
    def _push_data_to_url(self, data, url):
        self.stdout.write(f"Attempting to push data to URL: {url}")
        self.stdout.write(f"Payload being sent: {json.dumps(data, indent=2)}")
        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, json=data, headers=headers)
            self.stdout.write(f"Raw server response: {response.status_code} {response.text}")
            if response.ok:
                self.stdout.write(self.style.SUCCESS(f"Data successfully pushed to URL. Status Code: {response.status_code}"))
                self.stdout.write(f"Response: {response.text}")
            else:
                self.stderr.write(self.style.ERROR(f"Failed to push data to URL. Status Code: {response.status_code}"))
                self.stderr.write(self.style.ERROR(f"Response: {response.text}"))
        except requests.exceptions.RequestException as e:
            self.stderr.write(self.style.ERROR(f"Network error or invalid URL when pushing data: {e}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred while pushing data: {e}"))


    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Windy.com cloud analysis automation...'))

        driver = None
        try:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--log-level=3")   # Suppress Chrome warnings/errors in console
            # For debugging, remove headless if you want to see the browser:
            # chrome_options.add_argument('--headless')
            # chrome_options.add_argument('--disable-gpu')
            # chrome_options.add_argument('--no-sandbox')
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            wait = WebDriverWait(driver, 20)

            while True:
                try:
                    self.stdout.write("\n" + "="*50)
                    self.stdout.write(f"STARTING NEW AUTOMATION CYCLE at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    self.stdout.write("="*50 + "\n")

                    current_raw_time = datetime.now()
                    current_time = self._round_to_nearest_minutes(current_raw_time, minutes=10)
                    forecast_time = current_time + timedelta(minutes=10)
                    timestamp_str = forecast_time.strftime('%Y%m%d_%H%M%S')
                    self.stdout.write(f"Analysis timestamp (rounded): {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    self.stdout.write(f"Forecast timestamp (+10 min): {forecast_time.strftime('%Y-%m-%d %H:%M:%S')}")

                    full_screenshots_dir, drag_images_dir, analyzed_crops_dir = self._get_image_analysis_directories(timestamp_str)
                    self.stdout.write(f"Output directories created/ensured for this run:\n   Full: {full_screenshots_dir}\n   Drag: {drag_images_dir}\n   Analyzed: {analyzed_crops_dir}")

                    full_ss_before, cropped_tn_path, full_ss_after = self._automate_screenshot_capture(
                        driver, wait, timestamp_str, full_screenshots_dir, drag_images_dir, analyzed_crops_dir
                    )

                    if not cropped_tn_path:
                        self.stderr.write(self.style.ERROR("Failed to get the cropped Tamil Nadu image. Skipping analysis and database storage for this cycle."))
                        time.sleep(300)
                        continue

                    self.stdout.write("\n--- Starting Image Analysis ---")
                    cloud_percentage = self._analyze_cloud_percentage(cropped_tn_path)

                    if cloud_percentage is not None:
                        forecast_time = current_time + timedelta(minutes=10)
                        location_name = "Ramanathapuram"

                        self.stdout.write("\n--- Storing Data to Database ---")
                        self._store_data_to_db(
                            timestamp=forecast_time,
                            location_name=location_name,
                            cloud_percentage=cloud_percentage,
                            full_screenshot_path=full_ss_before,
                            drag_image_path=cropped_tn_path
                        )

                        json_data = {
                            "timestamp": forecast_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "city": location_name,
                            "values": f"{cloud_percentage:.2f}%",
                            "type": "adhani_solar"
                        }
                        base_image_dir = os.path.dirname(full_screenshots_dir)
                        json_output_path = os.path.join(base_image_dir, f"cloud_analysis_{forecast_time.strftime('%Y%m%d_%H%M%S')}.json")
                        with open(json_output_path, "w") as f:
                            json.dump(json_data, f, indent=4)
                        self.stdout.write(self.style.SUCCESS(f"JSON data saved locally to: {json_output_path}"))

                        self._push_data_to_url(json_data, self.API_ENDPOINT_URL)
                    else:
                        self.stderr.write(self.style.WARNING("Cloud percentage analysis failed. Data not stored to DB or pushed for this cycle."))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"Error in automation cycle: {e}"))
                finally:
                    self.stdout.write("\nFinished current automation cycle. Waiting for next run...\n")
                    time.sleep(600)

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Critical error in main automation loop: {e}"))
        finally:
            if driver:
                driver.quit()
                self.stdout.write("Browser closed.")