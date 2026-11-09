package com.adpulse.main.safeheron.security;

import com.safeheron.client.utils.RsaUtil;
import java.security.KeyFactory;
import java.security.interfaces.RSAPrivateCrtKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.RSAPublicKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;

/** 入库前规范化RSA凭证并通过SDK签名自检，不调用远端接口或输出密钥。 */
public final class SafeheronKeyValidator {
    private SafeheronKeyValidator() {}

    /** 接受未加密PKCS#8 PEM或Base64正文，返回SDK可直接使用的正文。 */
    public static String privateKey(String raw) {
        try {
            String normalized = normalize(raw, "PRIVATE KEY");
            KeyFactory factory = KeyFactory.getInstance("RSA");
            var key =
                    factory.generatePrivate(
                            new PKCS8EncodedKeySpec(Base64.getDecoder().decode(normalized)));
            if (!(key instanceof RSAPrivateCrtKey rsa)) throw new IllegalArgumentException();
            var publicKey =
                    factory.generatePublic(
                            new RSAPublicKeySpec(rsa.getModulus(), rsa.getPublicExponent()));
            String publicBody = Base64.getEncoder().encodeToString(publicKey.getEncoded());
            String challenge = "adpulse-safeheron-key-validation";
            if (!RsaUtil.verifySign(challenge, RsaUtil.sign(challenge, normalized), publicBody)) {
                throw new IllegalArgumentException();
            }
            return normalized;
        } catch (Exception exception) {
            // 不透传解析器或SDK异常，避免凭证内容进入响应或日志。
            throw new IllegalArgumentException(
                    "Safeheron私钥校验失败：请提交完整的未加密PKCS#8 RSA私钥，确认内容未损坏且可正常签名");
        }
    }

    /** 校验平台RSA公钥的X.509格式；平台公钥不是客户端私钥对应的公钥。 */
    public static String publicKey(String raw) {
        try {
            String normalized = normalize(raw, "PUBLIC KEY");
            KeyFactory.getInstance("RSA")
                    .generatePublic(new X509EncodedKeySpec(Base64.getDecoder().decode(normalized)));
            return normalized;
        } catch (Exception exception) {
            throw new IllegalArgumentException("Safeheron公钥校验失败：请提交完整的X.509 RSA平台公钥");
        }
    }

    private static String normalize(String raw, String label) {
        if (raw == null || raw.isBlank()) throw new IllegalArgumentException();
        String value = raw.trim().replace("\\r", "\r").replace("\\n", "\n");
        String begin = "-----BEGIN " + label + "-----";
        String end = "-----END " + label + "-----";
        if (value.startsWith(begin) && value.endsWith(end)) {
            value = value.substring(begin.length(), value.length() - end.length());
        }
        value = value.replaceAll("\\s", "");
        // 使用严格Base64解码，不静默忽略错误头尾、反斜杠或其他非法字符。
        return Base64.getEncoder().encodeToString(Base64.getDecoder().decode(value));
    }
}
