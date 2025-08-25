# azure_ip_change

Quickly change the public ip of an azure virtual machine

快速修改azure虚拟机公网ip

## 一 使用

### 1 获取登录认证的参数，填入配置文件

#### 1.1登录账号，进入cloudshell，如图

<img width="709" height="157" alt="image" src="https://github.com/user-attachments/assets/729971b6-00ff-44ea-bc0b-eab20a8b022b" />

#### 1.2 输入一下命令

```
az ad sp create-for-rbac --role contributor --scopes /subscriptions/$(az account list --query [].id -o tsv)
```

返回类似内容

<img width="1248" height="300" alt="image" src="https://github.com/user-attachments/assets/580aebf8-f85f-46e6-a879-12e2123692e4" />

#### 1.3 在配置文件中填写

<img width="382" height="234" alt="image" src="https://github.com/user-attachments/assets/c31238a3-08f0-4cc1-9fcc-ac05eb60e119" />

### 2 把配置文件和exe程序放在同一个文件夹中，运行exe即可看到配置的账号信息，一路手动即可，默认选择第一个，效果如图：

<img width="549" height="887" alt="image" src="https://github.com/user-attachments/assets/052bf4aa-e874-4ba1-b475-6982b0f58ed3" />

