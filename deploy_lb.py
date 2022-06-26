import json
import time
import os
import shutil
import sys
from subprocess import check_output
from datetime import datetime
from xxlimited import Null
from dateutil.parser import *
import paramiko
import threading

image = 'ami-0947d2ba12ee1ff75' # Free tier Amazon Linux 2 AMI
fname = 'ex2_cloud'
path = os.getcwd() + '/' + fname

# Set key name here
key_name = str(int(time.time()))

# Zip upload folder
zip_path = shutil.make_archive(fname, 'zip', fname)
zip_fname = fname + '.zip'

def instance_config(inst, key_name, access_key, access_secret_key, region, vpc_id, dns_inst):
    # Wait until status checks complete
    while True:
        output = aws_cli('aws ec2 describe-instance-status --instance-id {}'.format(inst))
        if len(output['InstanceStatuses']):
            if output['InstanceStatuses'][0]['InstanceStatus']['Status'] == 'initializing':
                print('initializing, waiting 10 seconds...')
                time.sleep(10)
            else:
                break
        else:
            print('waiting 10 seconds...')
            time.sleep(10)

    # Get public DNS
    output = aws_cli('aws ec2 describe-instances --instance-id {}'.format(inst))
    dns = output['Reservations'][0]['Instances'][0]['PublicDnsName']

    # Initialize SSHClient w/paramiko
    k = paramiko.RSAKey.from_private_key_file(
        "{}.pem".format(key_name)
    )
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # SSHClient connect is the most finicky part, if you miss anything from above \
    # (mismatched regions, no automatically assigned IP addresses, no inbound rules for security group), \
    # this will fail to connect.
    c.connect(hostname=dns, username="ec2-user", pkey=k)

    # Upload docker image
    cmd = 'sudo yum update'
    stdin, stdout, stderr = c.exec_command('sudo yum update')
    stdin, stdout, stderr = c.exec_command('sudo amazon-linux-extras install docker')

    sftp = c.open_sftp()

    # Upload zip file
    upload = sftp.put(
        zip_path,
        '/home/ec2-user/' + zip_fname
    )
    # .read() will read until EOF, causing the script to run forever
    # use .shutdown_write() and sys to close the channel before reading
    def exec_shutdown_write(c, command, t=1000):
        stdin, stdout, stderr = c.exec_command(command, timeout=t)
        stdout.channel.shutdown_write()
        return sys.stdout.write(str(stdout.read()))

    # Unzip
    exec_shutdown_write(c, 'unzip -o ' + fname)

    # Check if upload complete
    exec_shutdown_write(c, 'ls')

    # Build docker image
    exec_shutdown_write(c, 'sudo amazon-linux-extras install docker')
    x = exec_shutdown_write(c, 'sudo amazon-linux-extras install docker')
    x = exec_shutdown_write(c, 'sudo service docker start')
    x = exec_shutdown_write(c,'sudo curl -L "https://github.com/docker/compose/releases/download/v2.6.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose')
    x = exec_shutdown_write(c,"sudo chmod +x /usr/local/bin/docker-compose")
    x = exec_shutdown_write(c,'sudo service docker start')
    x = exec_shutdown_write(c,'sudo usermod -a -G docker ec2-user')
    x = exec_shutdown_write(c,'sudo chmod 666 /var/run/docker.sock')
    # after unzip 
    exec_shutdown_write(c, 'printf "ACCESSKEY={}\n ACCESSSECRETKEY={}\n REGION={}\n VPC={}\n OTHERDNS={}" > .env'.format(access_key, access_secret_key, region, vpc_id, dns_inst))
    x = exec_shutdown_write(c, 'docker-compose --env-file .env up -d')
    c.close()


# Inner folder of upload (to run later)
inner = os.listdir(fname)[0]

def aws_cli(command):
    output = check_output(
        command,
        shell=True
    )
    if output != b'':
        try:
            output = json.loads(output)
        except ValueError as e:
            output = output.decode('ascii').strip()
        return output

access_key = input("Please enter AWS accessKey")
access_secret_key = input("Please enter AWS access Secret key")
region = input('Please enter region')

# set up details
aws_cli('aws configure set aws_access_key_id {}; aws configure set aws_secret_access_key {};aws configure set region {};'.format(access_key, access_secret_key, region))

# Get default VPC
output = aws_cli('aws ec2 describe-vpcs --filter "Name=isDefault,Values=true"')
vpc = output['Vpcs'][0]['VpcId']

# Create key
output = aws_cli("aws ec2 create-key-pair --key-name {} --output text > {}.pem".format(key_name, key_name))

# The key is generating with fingerprint up front, which confuses paramiko
key_str = open('{}.pem'.format(key_name), 'r').read()

# Have to remove the fingerprint up front for some reason
with open('{}.pem'.format(key_name), 'w') as w:
    w.write(key_str[key_str.index('-----'):])
key_str = open('{}.pem'.format(key_name), 'r').read()

print(sys.argv)
sg_id = sys.argv[1]
subnet_public_first_id = sys.argv[2]
subnet_public_second_id = sys.argv[3]
vpc_id = sys.argv[4]

# sg_id = "sg-068b6cba76d14d627"
# subnet_public_first_id = "subnet-0c59a1b80ecec3a0e"
# subnet_public_second_id = "subnet-06ef963ac3efc30ec"
# vpc_id = "vpc-014adac182ea921b9"

# Runs EC2
output1 = aws_cli("aws ec2 run-instances --image-id {} --count 1 --instance-type t2.micro --key-name {} --security-group-ids {} --subnet-id {}".format(image, key_name, sg_id, subnet_public_first_id))
inst1 = output1['Instances'][0]['InstanceId']

while(aws_cli(("aws ec2 describe-instance-status --instance-id {} --query InstanceStatuses[].InstanceState[].Name[]").format(inst1)) != ['running']):
    print('waiting for runnig ec2 1 to get public dns...')
dns_inst1 = aws_cli(('aws ec2 describe-instances --instance-ids {} --query Reservations[].Instances[][].PublicDnsName').format(inst1))[0]


output2 = aws_cli("aws ec2 run-instances --image-id {} --count 1 --instance-type t2.micro --key-name {} --security-group-ids {} --subnet-id {}".format(image, key_name, sg_id, subnet_public_second_id))
inst2 = output2['Instances'][0]['InstanceId']

while(aws_cli(("aws ec2 describe-instance-status --instance-id {} --query InstanceStatuses[].InstanceState[].Name[]").format(inst2)) != ['running']):
    print('waiting for runnig ec2 2 to get public dns...')
dns_inst2 = aws_cli(('aws ec2 describe-instances --instance-ids {} --query Reservations[].Instances[][].PublicDnsName').format(inst2))[0]

threading.Thread(target=instance_config, args=(inst1, key_name, access_key, access_secret_key, region, vpc_id, dns_inst2)).start()

time.sleep(20)

threading.Thread(target=instance_config, args=(inst2, key_name, access_key, access_secret_key, region, vpc_id, dns_inst1)).start()

# Load balancer
# Create the classic load balancer
subnets = subnet_public_first_id  + " " + subnet_public_second_id
AWS_CLB_DNS = aws_cli(('aws elb create-load-balancer --load-balancer-name my-lb6 --listeners "Protocol=HTTP,LoadBalancerPort=80,InstanceProtocol=HTTP,InstancePort=80" --subnets {} --security-groups {} --query "DNSName" --output text').format(subnets, sg_id))
 
# Register both the instances with load balancer
instances_ids = inst1 + " " + inst2
aws_cli(('aws elb register-instances-with-load-balancer --load-balancer-name my-lb6 --instances {}').format(instances_ids))
print("LB address is " + AWS_CLB_DNS)
