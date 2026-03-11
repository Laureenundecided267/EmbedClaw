#include <stdbool.h>

#include "esp_spiffs.h"

#include "ec_config.h"
#include "support/ec_test_hooks.h"

static bool s_spiffs_mounted = false;

esp_err_t ec_test_spiffs_mount(void)
{
    if (s_spiffs_mounted) {
        return ESP_OK;
    }

    esp_vfs_spiffs_conf_t conf = {
        .base_path = EC_FS_BASE,
        .partition_label = NULL,
        .max_files = 16,
        .format_if_mount_failed = true,
    };

    esp_err_t err = esp_vfs_spiffs_register(&conf);
    if (err == ESP_OK) {
        s_spiffs_mounted = true;
    }

    return err;
}

void ec_test_spiffs_unmount(void)
{
    if (!s_spiffs_mounted) {
        return;
    }

    esp_vfs_spiffs_unregister(NULL);
    s_spiffs_mounted = false;
}
