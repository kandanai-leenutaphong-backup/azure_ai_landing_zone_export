// Generic Linux VM module (parametrized), reused for myVm and vm-2.
// Includes SSH key, NIC (with its own NSG, matching the original 1-NSG-per-VM layout),
// and the Microsoft Defender for Endpoint (MDE.Linux) extension.

@description('Region.')
param location string = 'southeastasia'

@description('VM name.')
param vmName string

@description('SSH public key resource name.')
param sshKeyName string

@description('SSH public key data (paste the existing key material before deploying).')
@secure()
param sshPublicKey string

@description('NIC resource name.')
param nicName string

@description('Subnet resource ID (snet-vm).')
param subnetId string

@description('NSG resource ID dedicated to this VM\'s NIC.')
param nsgId string

@description('Admin username.')
param adminUsername string = 'azureuser'

@description('VM size.')
param vmSize string = 'Standard_B2s'

@description('Managed OS disk SKU.')
param osDiskStorageAccountType string = 'Standard_LRS'

@description('Assign a public IP to this VM\'s NIC (set false once Bastion-only access is desired).')
param assignPublicIp bool = false

@description('Install the Microsoft Defender for Endpoint extension. Requires Defender for Servers/MDE onboarding to be configured.')
param enableMdeExtension bool = false

param tags object = {}

resource sshKey 'Microsoft.Compute/sshPublicKeys@2024-07-01' = {
  name: sshKeyName
  location: location
  tags: tags
  properties: {
    publicKey: sshPublicKey
  }
}

resource pip 'Microsoft.Network/publicIPAddresses@2023-11-01' = if (assignPublicIp) {
  name: '${vmName}-pip'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource nic 'Microsoft.Network/networkInterfaces@2023-11-01' = {
  name: nicName
  location: location
  tags: tags
  properties: {
    networkSecurityGroup: {
      id: nsgId
    }
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: {
            id: subnetId
          }
          privateIPAllocationMethod: 'Dynamic'
          publicIPAddress: assignPublicIp ? {
            id: pip.id
          } : null
        }
      }
    ]
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' = {
  name: vmName
  location: location
  tags: tags
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    osProfile: {
      computerName: vmName
      adminUsername: adminUsername
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: sshKey.properties.publicKey
            }
          ]
        }
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: osDiskStorageAccountType
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
        }
      ]
    }
  }
}

resource mdeExtension 'Microsoft.Compute/virtualMachines/extensions@2024-07-01' = if (enableMdeExtension) {
  parent: vm
  name: 'MDE.Linux'
  location: location
  tags: tags
  properties: {
    publisher: 'Microsoft.Azure.AzureDefenderForServers'
    type: 'MDE.Linux'
    typeHandlerVersion: '1.0'
    autoUpgradeMinorVersion: true
    settings: {
      autoUpdate: true
    }
  }
}

output vmId string = vm.id
output nicId string = nic.id
