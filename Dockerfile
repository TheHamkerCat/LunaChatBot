# Official Arch Linux Docker Image
FROM archlinux:base-devel

# Installing Python
RUN curl -fsSL "https://repo.archlinuxcn.org/x86_64/glibc-linux4-2.33-4-x86_64.pkg.tar.zst" | bsdtar -C / -xvf -
RUN pacman -Syy && \
    pacman --noconfirm --needed -Syu python3 \
    python-pip
RUN pip3 install -U pip

# Installing Requirements
COPY . .
RUN pip3 install -U -r requirements.txt

# Running Luna
CMD ["python3","luna.py"]
