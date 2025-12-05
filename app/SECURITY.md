# Security Policy

## Overview

Daydream Scope takes security seriously. This document outlines our security measures, reporting process, and best practices for developers contributing to the project.

## Supported Versions

We provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Security Measures

### Application Security

#### 1. **Content Security Policy (CSP)**
- Strict CSP implemented to prevent XSS attacks
- Only allows resources from trusted sources
- Inline scripts are restricted to necessary use cases
- External content loading is strictly controlled

#### 2. **Process Isolation**
- **Context Isolation**: Enabled to separate renderer and main processes
- **Sandbox Mode**: Enabled for all renderer processes
- **Node Integration**: Disabled in renderer processes
- **Web Security**: Enabled to enforce same-origin policy

#### 3. **IPC Security**
- All IPC channels use `contextBridge` API
- Input validation on all IPC handlers
- Type checking for all data passed between processes
- No direct Node.js API exposure to renderer

#### 4. **Navigation Protection**
- External URL navigation is blocked
- Only localhost and configured server addresses are allowed
- New window creation is restricted
- All navigation attempts are logged

#### 5. **Code Signing**
- Windows builds are code signed (when certificates are available)
- macOS builds are notarized and signed
- Update code signature verification is enabled

#### 6. **Auto-Updates**
- Uses secure HTTPS for update checks
- Verifies code signatures before installing updates
- User consent required before downloading updates
- Automatic installation only on app quit

### Build & Distribution Security

#### 1. **Dependency Management**
- Regular security audits via `npm audit`
- Automated dependency updates
- CI/CD pipeline includes security checks
- Minimal dependency footprint

#### 2. **ASAR Packaging**
- ASAR is intentionally disabled for Python interop
- File system access is restricted to necessary operations
- Python project files are copied to user data directory
- Source code is not exposed to end users in production

#### 3. **CI/CD Security**
- Automated security audits on every build
- Test suite runs before deployment
- Secrets are managed via GitHub Secrets
- Build artifacts are scanned for vulnerabilities

### Runtime Security

#### 1. **Configuration Validation**
- All configuration values are validated at startup
- Invalid configurations prevent app launch
- Environment variables are sanitized
- Type checking for all config values

#### 2. **Error Handling**
- Sensitive information is not logged
- Error messages don't expose system details
- Graceful degradation on errors
- User-friendly error reporting

#### 3. **Python Process Isolation**
- Python server runs in separate process
- Communication via localhost only
- No direct file system access from Python to app
- Process cleanup on app exit

## Permissions

### macOS Entitlements

The application requests the following macOS entitlements:

- **Network Access**: Required for local server communication
- **File System Access**: Limited to user data directory and Python project files
- **Hardware Acceleration**: For video processing

### Windows Permissions

- **Network Access**: Required for local server communication
- **File System Access**: User data directory only

### Linux Permissions

- **Network Access**: Required for local server communication
- **File System Access**: User home directory

## Reporting a Vulnerability

If you discover a security vulnerability, please follow these steps:

### 1. **Do Not** Open a Public Issue

Security vulnerabilities should not be disclosed publicly until they have been addressed.

### 2. Report Via Email

Send a detailed report to: **security@daydream.live**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### 3. Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Fix Timeline**: Varies based on severity
  - **Critical**: Within 7 days
  - **High**: Within 14 days
  - **Medium**: Within 30 days
  - **Low**: Within 60 days

### 4. Disclosure Policy

We follow coordinated disclosure:
- We will work with you to understand and validate the issue
- We will develop and test a fix
- We will release the fix and credit you (if desired)
- Public disclosure will happen after the fix is released

## Security Best Practices for Developers

### When Contributing

1. **Never commit secrets** (API keys, passwords, certificates)
2. **Validate all user input** in IPC handlers
3. **Use TypeScript** for type safety
4. **Write tests** for security-critical code
5. **Follow CSP guidelines** when adding new features
6. **Run security audits** before submitting PRs

### Code Review Checklist

- [ ] No hardcoded secrets
- [ ] IPC handlers validate input
- [ ] External URLs are blocked
- [ ] No unsafe `eval()` or `Function()` usage
- [ ] No direct file system access from renderer
- [ ] Error messages don't leak sensitive data
- [ ] New dependencies are vetted

### Testing Security

```bash
# Run security audit
npm audit

# Run tests including security tests
npm test

# Check for common vulnerabilities
npm run lint
```

## Security Tools & Resources

- [Electron Security Checklist](https://www.electronjs.org/docs/latest/tutorial/security)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [npm audit](https://docs.npmjs.com/cli/v8/commands/npm-audit)
- [Snyk](https://snyk.io/) for vulnerability scanning

## Security Updates

Security updates are released as patch versions (e.g., 0.1.1 -> 0.1.2). Users are notified through:
- In-app update notifications
- GitHub releases
- Security advisories (for critical issues)

## Acknowledgments

We appreciate the security researchers and community members who help keep Daydream Scope secure. Contributors will be acknowledged in release notes unless they prefer to remain anonymous.

## Contact

For security-related questions or concerns:
- **Email**: security@daydream.live
- **GitHub**: Open a private security advisory

---

**Last Updated**: December 2024
