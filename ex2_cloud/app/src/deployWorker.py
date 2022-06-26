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

def deploy(key, s_key, region, host_name, instance_id=0):
    image = 'ami-0947d2ba12ee1ff75' # Free tier Amazon Linux 2 AMI
    fname = 'src2'
    path = os.getcwd() + '/' + fname

    # Set key name here
    key_name = str(int(time.time()))

    # Zip upload folder
    zip_path = shutil.make_archive(fname, 'zip', fname)
    zip_fname = fname + '.zip'

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

    aws_cli('aws configure set aws_access_key_id {}; aws configure set aws_secret_access_key {};'.format(key, s_key))

    if instance_id != 0:
        aws_cli('delete-instance --instance-id {}'.format(instance_id))
    # Get default VPC
    output = aws_cli('aws ec2 describe-vpcs --filter "Name=isDefault,Values=true"')
    print(output)
    vpc = output['Vpcs'][0]['VpcId']

    # Get subnet for default VPC
    output = aws_cli('aws ec2 describe-subnets --filter "Name=vpc-id,Values={}"'.format(vpc))
    print(output)
    subnet = output['Subnets'][0]['SubnetId']

    # Make new security group
    # Note: needs to belong to proper network (same as subnet)
    output = aws_cli("aws ec2 create-security-group --vpc-id {} --group-name {} --description {}".format(vpc, key_name, key_name))
    print(output)
    sg = output['GroupId']

    # Edit inbound rules
    output = aws_cli('aws ec2 authorize-security-group-ingress --group-id {} --protocol tcp --port 22 --cidr 0.0.0.0/0'.format(sg))
    output = aws_cli('aws ec2 authorize-security-group-ingress --group-id {} --protocol tcp --port 4369 --cidr 0.0.0.0/0'.format(sg))
    output = aws_cli('aws ec2 authorize-security-group-ingress --group-id {} --protocol tcp --port 15672 --cidr 0.0.0.0/0'.format(sg))
    output = aws_cli('aws ec2 authorize-security-group-ingress --group-id {} --protocol tcp --port 5672 --cidr 0.0.0.0/0'.format(sg))

    # Create key
    output = aws_cli("aws ec2 create-key-pair --key-name {} --output text > {}.pem".format(key_name, key_name))

    # The key is generating with fingerprint up front, which confuses paramiko (later in script)
    key_str = open('{}.pem'.format(key_name), 'r').read()

    # Have to remove the fingerprint up front for some reason
    with open('{}.pem'.format(key_name), 'w') as w:
        w.write(key_str[key_str.index('-----'):])
    key_str = open('{}.pem'.format(key_name), 'r').read()
    print(key_str)

    # Runs EC2
    output = aws_cli("aws ec2 run-instances --image-id {} --count 1 --instance-type t2.micro --key-name {} --security-group-ids {} --subnet-id {}".format(image, key_name, sg, subnet))
    print(output)
    inst = output['Instances'][0]['InstanceId']

    # Wait until status checks complete
    while True:
        output = aws_cli('aws ec2 describe-instance-status --instance-id {}'.format(inst))
        if len(output['InstanceStatuses']):
            if output['InstanceStatuses'][0]['InstanceStatus']['Status'] == 'initializing':
                print('initializing, waiting 10 seconds...')
                time.sleep(10)
            else:
                print(output)
                break
        else:
            print('waiting 10 seconds...')
            time.sleep(10)

    # Get public DNS
    output = aws_cli('aws ec2 describe-instances --instance-id {}'.format(inst))
    print(output)
    dns = output['Reservations'][0]['Instances'][0]['PublicDnsName']

    # Initialize SSHClient w/paramiko
    k = paramiko.RSAKey.from_private_key_file(
        "{}.pem".format(key_name)
    )
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # SSHClient connect 
    c.connect(hostname=dns, username="ec2-user", pkey=k)

    # Upload docker image
    cmd = 'sudo yum update'
    stdin, stdout, stderr = c.exec_command('sudo yum update')
    stdin, stdout, stderr = c.exec_command('sudo amazon-linux-extras install docker')
    stdin, stdout, stderr = c.exec_command('sudo service docker start')
    stdin, stdout, stderr = c.exec_command('sudo usermod -a -G docker ec2-user')
    stdin, stdout, stderr = c.exec_command('sudo chmod 666 /var/run/docker.sock')

    sftp = c.open_sftp()

    # Upload zip file
    upload = sftp.put(
        zip_path,
        '/home/ec2-user/' + zip_fname
    )

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
    x = exec_shutdown_write(c,'sudo curl -L "https://github.com/docker/compose/releases/download/1.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose')
    x = exec_shutdown_write(c,"sudo chmod +x /usr/local/bin/docker-compose")
    
    # after unzip 
    exec_shutdown_write(c, 'echo "RABBIT={}" > .env'.format(host_name))
    x = exec_shutdown_write(c, 'docker-compose --env-file .env up -d')
    c.close()

if __name__ == "__main__":
   deploy()