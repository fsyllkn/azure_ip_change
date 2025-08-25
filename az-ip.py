# ==============================================================================
# Azure VM Public IP 更新脚本 (Azure SDK for Python 版)
#
# 功能:
#   - 使用原生 Azure SDK，无需在 PC 上安装 Azure CLI。
#   - 可通过 PyInstaller 打包成独立的 .exe 文件。
#   - 从配置文件读取并让用户选择多个 Azure 账号。
#   - 自动完成 IP 的解绑、创建、绑定和清理。
#
# 运行前请先安装依赖库:
# pip install azure-identity azure-mgmt-resource azure-mgmt-compute azure-mgmt-network
# ==============================================================================

import configparser
import os
import sys
import time

# 导入 Azure SDK 相关的库
from azure.identity import ClientSecretCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.core.exceptions import HttpResponseError

# 配置文件路径
CONFIG_FILE_PATH = "/config/azure.conf"
LOCAL_CONFIG_FILE_PATH = "my_azure_creds.conf"


def select_from_list(items, prompt, display_key=None):
    """
    显示一个列表并让用户选择。
    :param items: 要选择的项的列表。
    :param prompt: 显示给用户的提示信息。
    :param display_key: 如果列表项是字典，使用这个键来显示。
    :return: 用户选择的项。
    """
    if not items:
        print(f"错误: 未找到任何 {prompt}。")
        sys.exit(1)

    print(f"\n请从以下 {prompt} 中选择一个:")
    for i, item in enumerate(items, 1):
        display_text = item[display_key] if display_key else item
        print(f"  {i}) {display_text}")

    try:
        choice_str = input(f"请输入编号 (默认为 1): ")
        choice = int(choice_str) if choice_str else 1
        
        if 1 <= choice <= len(items):
            return items[choice - 1]
        else:
            print("错误: 无效的选择。")
            sys.exit(1)
    except ValueError:
        print("错误: 无效的输入。")
        sys.exit(1)


def main():
    """主执行函数"""
    # 1. 读取和选择 Azure 凭据
    config = configparser.ConfigParser()
    
    effective_config_path = ""
    # 优先使用容器内的路径
    if os.path.exists(CONFIG_FILE_PATH):
        effective_config_path = CONFIG_FILE_PATH
    # 否则使用本地路径
    elif os.path.exists(LOCAL_CONFIG_FILE_PATH):
        effective_config_path = LOCAL_CONFIG_FILE_PATH
    else:
        print(f"错误: 在脚本目录或 /config/ 中未找到配置文件 'my_azure_creds.conf'。")
        sys.exit(1)

    print(f"找到配置文件: {effective_config_path}，正在加载...")
    config.read(effective_config_path, encoding='utf-8')

    accounts = []
    for section in config.sections():
        if section.startswith('ACCOUNT_'):
            account_details = dict(config[section])
            account_details['section_name'] = section
            accounts.append(account_details)

    if not accounts:
        print("错误: 在配置文件中没有找到任何有效格式的账号 (例如 [ACCOUNT_1])。")
        sys.exit(1)
    
    # 创建用于显示的选择列表
    account_display_list = [
        {'display': acc.get('az_account_name', f"订阅ID: {acc.get('az_subscription_id')}"), 'data': acc}
        for acc in accounts
    ]

    selected_account_display = select_from_list(account_display_list, "Azure 账号", display_key='display')
    creds = selected_account_display['data']
    
    app_id = creds['az_app_id']
    tenant_id = creds['az_tenant_id']
    password = creds['az_password']
    subscription_id = creds['az_subscription_id']
    
    print(f"已选择账号: {selected_account_display['display']}")

    # 2. 使用 SDK 进行认证并创建客户端
    try:
        print("\n正在使用服务主体登录 Azure...")
        credential = ClientSecretCredential(tenant_id=tenant_id, client_id=app_id, client_secret=password)
        
        resource_client = ResourceManagementClient(credential, subscription_id)
        compute_client = ComputeManagementClient(credential, subscription_id)
        network_client = NetworkManagementClient(credential, subscription_id)
        print("登录成功。")
    except Exception as e:
        print(f"登录失败，请检查所选账号的凭据是否正确。错误: {e}")
        sys.exit(1)

    # 3. 选择资源组
    resource_groups_pager = resource_client.resource_groups.list()
    resource_groups = [rg.name for rg in resource_groups_pager]
    resource_group_name = select_from_list(resource_groups, "资源组")
    print(f"已选择资源组: {resource_group_name}")

    # 4. 选择虚拟机
    vms_pager = compute_client.virtual_machines.list(resource_group_name)
    vms = [vm.name for vm in vms_pager]
    vm_name = select_from_list(vms, "虚拟机")
    print(f"已选择虚拟机: {vm_name}")
    
    timestamp = int(time.time())
    new_public_ip_name = f"{vm_name}-ip-{timestamp}"

    # 5. 获取 NIC 信息
    print("\n正在获取虚拟机网络接口信息...")
    vm = compute_client.virtual_machines.get(resource_group_name, vm_name)
    nic_id = vm.network_profile.network_interfaces[0].id
    nic_name = nic_id.split('/')[-1]
    print(f"已找到网络接口名称: {nic_name}")

    nic = network_client.network_interfaces.get(resource_group_name, nic_name)
    nic_location = nic.location
    ip_config = nic.ip_configurations[0]
    ip_config_name = ip_config.name
    print(f"已找到网络接口位置: {nic_location}")
    print(f"已找到 IP 配置名称: {ip_config_name}")

    # 6. 解除旧 IP 关联
    print("\n正在获取旧的公共IP名称并解除关联...")
    if ip_config.public_ip_address:
        old_public_ip_id = ip_config.public_ip_address.id
        old_public_ip_name = old_public_ip_id.split('/')[-1]
        print(f"找到旧的公共IP: {old_public_ip_name}")
        
        ip_config.public_ip_address = None
        
        poller = network_client.network_interfaces.begin_create_or_update(resource_group_name, nic_name, nic)
        poller.result() # 等待操作完成
        print(f"已成功解除旧公共IP: {old_public_ip_name} 的关联。")
    else:
        print("警告：虚拟机没有关联公共IP，将直接创建新IP。")

    # 7. 创建新 IP
    print(f"\n正在创建新的公共IP: {new_public_ip_name}...")
    ip_params = {
        "location": nic_location,
        "sku": {"name": "Standard"},
        "public_ip_allocation_method": "Static"
    }
    poller = network_client.public_ip_addresses.begin_create_or_update(resource_group_name, new_public_ip_name, ip_params)
    new_ip_object = poller.result()
    print("新公共IP创建成功。")

    # 8. 关联新 IP
    print("\n正在将新的公共IP关联到网络接口...")
    # 重新获取最新的 NIC 对象
    nic = network_client.network_interfaces.get(resource_group_name, nic_name)
    nic.ip_configurations[0].public_ip_address = new_ip_object
    
    poller = network_client.network_interfaces.begin_create_or_update(resource_group_name, nic_name, nic)
    updated_nic = poller.result()
    
    new_ip_address = network_client.public_ip_addresses.get(resource_group_name, new_public_ip_name).ip_address
    
    print("\n==========================================")
    print("IP地址更新完成！")
    print(f"新的公共IP名称: {new_public_ip_name}")
    print(f"新的公共IP地址: {new_ip_address}")
    print("==========================================")

    # 9. 清理未关联的 IP
    print("\n正在查找并清理资源组中所有未关联的公共IP...")
    public_ips_pager = network_client.public_ip_addresses.list(resource_group_name)
    unused_ips = [ip for ip in public_ips_pager if ip.ip_configuration is None]

    if not unused_ips:
        print("没有发现未关联的公共IP。")
    else:
        print("发现以下未关联的公共IP，将进行删除：")
        for ip in unused_ips:
            print(f" - {ip.name}")
            try:
                poller = network_client.public_ip_addresses.begin_delete(resource_group_name, ip.name)
                poller.result()
                print(f"已成功删除 {ip.name}。")
            except HttpResponseError as e:
                print(f"警告：删除公共IP '{ip.name}' 失败: {e.message}")
            
    print("\n==========================================")
    print("所有操作完成！")
    print("==========================================")
    os.system("pause") if os.name == 'nt' else input("按 Enter 键退出...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n发生了一个意外错误: {e}")
        print("脚本已终止。")
        os.system("pause") if os.name == 'nt' else input("按 Enter 键退出...")
        sys.exit(1)

