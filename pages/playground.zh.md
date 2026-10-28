# 在线演练

《应用后量子密码学》中的每一个算法都有 SageMath 实现，下面的单元格直接在浏览器中运行它们，无需安装，也无需下载任何东西。编辑任意单元格，然后点击**运行**。

代码并没有复制到本页中。每个单元格都直接从[代码仓库](https://github.com/AppliedPQC/AppliedPQC/tree/main/sage)获取 `.sage` 源文件，因此这里运行的正是书中所讲解的代码。

代码在免费的 [SageMath Cell](https://sagecell.sagemath.org/) 服务上执行，每次运行限时 30 秒。几乎所有内容都能在时限内完成；少数做不到的操作在下文注明，并给出在本地运行它们的命令。

下面是四个标准。书中其余的每一段代码（各章逐步搭建起来的格、LWE、NTT 和玩具版 Kyber 实验）同样可以运行，按章列在本页末尾。

## ML-KEM (FIPS 203)

在全部三个参数集上进行密钥生成、封装与解封装。封装密钥与解封装密钥得到相同的共享秘密，各项尺寸与 FIPS 203 表 3 一致。

<div class="sage"><script type="text/x-sage">import urllib.request
exec(urllib.request.urlopen("https://raw.githubusercontent.com/AppliedPQC/AppliedPQC/main/sage/playground.py").read())
apqc_load('fips203')
for ps in ['ML-KEM-512', 'ML-KEM-768', 'ML-KEM-1024']:
    kem = MLKEM(ps)
    ek, dk = kem.KeyGen()          # Algorithm 16
    K, c = kem.Encaps(ek)          # Algorithm 17
    K2 = kem.Decaps(dk, c)         # Algorithm 18
    print("%-12s shared secret agrees: %s   ek %d B, ct %d B"
          % (ps, K2 == K, len(ek), len(c)))
</script></div>

数论变换是一个*环同构*，而不只是一种快速乘法技巧。这项检查以 Sage 自身的算术为基准，验证了这一论断的全部三个部分；它正是 ML-KEM 一章中讨论的那项检查。

<div class="sage"><script type="text/x-sage">import urllib.request
exec(urllib.request.urlopen("https://raw.githubusercontent.com/AppliedPQC/AppliedPQC/main/sage/playground.py").read())
apqc_load('fips203')
print("NTT is a ring isomorphism:", verify_ntt_is_a_ring_isomorphism())
</script></div>

## ML-DSA (FIPS 204)

签名采用带中止的 Fiat-Shamir，因此拒绝循环的迭代次数每次运行都不相同。公钥和签名的尺寸与 FIPS 204 表 2 一致。

<div class="sage"><script type="text/x-sage">import urllib.request
exec(urllib.request.urlopen("https://raw.githubusercontent.com/AppliedPQC/AppliedPQC/main/sage/playground.py").read())
apqc_load('fips204')
for ps in ['ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87']:
    dsa = MLDSA(ps)
    pk, sk = dsa.KeyGen()                        # Algorithm 1
    sig = dsa.Sign(sk, b"attack at dawn", b"")   # Algorithm 2
    ok = dsa.Verify(pk, b"attack at dawn", sig, b"")
    print("%-11s verifies: %s   pk %d B, sig %d B" % (ps, ok, len(pk), len(sig)))
</script></div>

## SLH-DSA (FIPS 205)

`f`（“快速”）参数集的签名速度足够快，可以在这里端到端运行。

<div class="sage"><script type="text/x-sage">import urllib.request
exec(urllib.request.urlopen("https://raw.githubusercontent.com/AppliedPQC/AppliedPQC/main/sage/playground.py").read())
apqc_load('fips205')
slh = SLHDSA('SLH-DSA-SHAKE-128f')
SK, PK = slh.slh_keygen()
sig = slh.slh_sign(b"hash-based signatures", b"", SK)
print("verifies:", slh.slh_verify(b"hash-based signatures", sig, b"", PK))
print("signature: %d bytes" % len(sig))
</script></div>

`s`（“小型”）参数集以签名时间换取签名尺寸，对它们签名所需的时间远超 30 秒。不过验证是快的方向，用时远不到一秒，因此由 `apqc_demo_sig` 从 NIST 的 ACVP 向量中提供一个签名，其余交给验证器完成。请注意这些签名比上面的 `f` 签名小了多少。

<div class="sage"><script type="text/x-sage">import urllib.request
exec(urllib.request.urlopen("https://raw.githubusercontent.com/AppliedPQC/AppliedPQC/main/sage/playground.py").read())
apqc_load('fips205')
for ps in ['SLH-DSA-SHAKE-128s', 'SLH-DSA-SHAKE-192s', 'SLH-DSA-SHAKE-256s']:
    pk, msg, sig = apqc_demo_sig(ps)
    ok = SLHDSA(ps).slh_verify_internal(msg, sig, pk)
    print("%-20s verifies: %s   signature %d B" % (ps, bool(ok), len(sig)))
</script></div>

## FN-DSA (FIPS 206, Falcon)

FIPS 206 仍在制定中，因此这里遵循第三轮的 Falcon 提交方案。有两项检查用时远不到一秒：用 Falcon 公布的测试向量检查高斯采样器，以及用多项式环中的精确算术检查浮点 FFT。

<div class="sage"><script type="text/x-sage">import urllib.request
exec(urllib.request.urlopen("https://raw.githubusercontent.com/AppliedPQC/AppliedPQC/main/sage/playground.py").read())
apqc_load('fips206')
print("SamplerZ matches Falcon's KAT:", verify_samplerz_kat())
print("FFT agrees with the exact ring:", verify_fft_against_exact_ring())
</script></div>

Falcon 的密钥生成要运行 NTRU 塔式求解器，需要的是几分钟而不是几秒钟，因此改由 `apqc_demo_key` 加载第三轮的 KAT 密钥。用它进行签名和验证都很快。

<div class="sage"><script type="text/x-sage">import urllib.request
exec(urllib.request.urlopen("https://raw.githubusercontent.com/AppliedPQC/AppliedPQC/main/sage/playground.py").read())
apqc_load('fips206')
sk, h = apqc_demo_key('FN-DSA-512')
fn = FNDSA('FN-DSA-512')
sig = fn.Sign(b"lattice signatures over NTRU", sk)
print("verifies:", fn.Verify(b"lattice signatures over NTRU", sig, h))
print("NTRU equation f*G - g*F = q holds:",
      verify_ntru_equation(sk['f'], sk['g'], sk['F'], sk['G']))
</script></div>

一个 Falcon-512 签名为 666 字节：1 个头部字节、40 字节的盐值，以及 625 字节压缩后的 `s2`。书中从采样器的高斯宽度以及“符号位、低七位、一元码”编码推导出这个数字；这个单元格在一个真实签名上检验该推导。公钥没有可利用的“短小”性质，每个系数要占满 14 比特。

<div class="sage"><script type="text/x-sage">import urllib.request
exec(urllib.request.urlopen("https://raw.githubusercontent.com/AppliedPQC/AppliedPQC/main/sage/playground.py").read())
apqc_load('fips206')
sk, h = apqc_demo_key('FN-DSA-512')
fn = FNDSA('FN-DSA-512')
r, s = fn.Sign(b"where the bytes go", sk)
print("header 1 + salt", len(r), "+ compressed s2", len(s),
      "=", 1 + len(r) + len(s), "bytes; the parameter set says", fn.sbytelen)
print("public key:", len(fn.encode_public_key(h)), "bytes = 1 + 14 *", fn.n, "/ 8")
s2 = Decompress(s, fn.slen, fn.n)
used = sum(1 + 7 + (abs(int(c)) >> 7) + 1 for c in s2)
print("bits the code actually used: %d of %d, %.2f per coefficient"
      % (used, fn.slen, used / fn.n))
print("entropy of a Gaussian at sigma = %.1f: %.2f bits per coefficient"
      % (fn.sigma, float(log(fn.sigma * sqrt(2 * pi * e), 2))))
print("share of coefficients with |c| < 128: %.2f"
      % (sum(1 for c in s2 if abs(int(c)) < 128) / fn.n))
</script></div>

## 浏览器中放不下的内容

有三件事超出了 30 秒的时间预算。`apqc_require` 会点名指出它们，并说明应当改为运行什么，而不是让单元格在时限处悄无声息地终止。

<div class="sage"><script type="text/x-sage">import urllib.request
exec(urllib.request.urlopen("https://raw.githubusercontent.com/AppliedPQC/AppliedPQC/main/sage/playground.py").read())
for op in ['FN-DSA-512.Keygen', 'FN-DSA-1024', 'SLH-DSA-s.sign', 'test_kat']:
    try:
        apqc_require(op)
    except RuntimeError as e:
        print(e); print()
</script></div>

要不受限制地运行全部内容，包括针对 NIST ACVP 向量的完整 462 项检查测试套件：

```sh
git clone https://github.com/AppliedPQC/AppliedPQC
cd AppliedPQC/sage
./fetch_vectors.sh
sage test_kat.sage
```
