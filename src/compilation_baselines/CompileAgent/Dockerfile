FROM gcc:13.2.0

# install openssh-server
RUN apt-get update && apt-get install -y openssh-server tree cmake vim proxychains4 git
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
ARG SSH_PASSWORD="root"
RUN echo "root:$SSH_PASSWORD" | chpasswd
RUN echo "cd /work" >> ~/.bashrc

# configure proxychains
RUN sed -i 's/^socks4\s\+127\.0\.0\.1\s\+[0-9]\+/socks5 192.168.0.1 29999/' /etc/proxychains4.conf

# COPY wrapper into /
COPY wrapper_compiler.sh /
COPY wrapper_strip.sh /
RUN chmod +x /wrapper_compiler.sh /wrapper_strip.sh

# move compiler to compiler-real
RUN mv /usr/local/bin/gcc /usr/local/bin/gcc-real && ln -s /wrapper_compiler.sh /usr/local/bin/gcc
RUN mv /usr/local/bin/g++ /usr/local/bin/g++-real && ln -s /wrapper_compiler.sh /usr/local/bin/g++
RUN mv /usr/bin/cc /usr/bin/cc-real && ln -s /wrapper_compiler.sh /usr/bin/cc
RUN mv /usr/local/bin/c++ /usr/local/bin/c++-real && ln -s /wrapper_compiler.sh /usr/local/bin/c++
RUN mv /usr/bin/strip /usr/bin/strip-real && ln -s /wrapper_strip.sh /usr/bin/strip

# make work dir
RUN mkdir /work

WORKDIR /work
