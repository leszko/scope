import { app, BrowserWindow, Tray, Menu, nativeImage, nativeTheme, globalShortcut } from 'electron';
import path from 'path';
import fs from 'fs';
import { AppState } from '../types/services';
import { IPC_CHANNELS } from '../types/ipc';
import { SERVER_CONFIG } from '../utils/config';
import { logger, getLogPath } from '../utils/logger';

export class ScopeElectronAppService {
  private appState: AppState;
  private tray: Tray | null = null;
  private logsWindow: BrowserWindow | null = null;

  constructor(appState: AppState) {
    this.appState = appState;
    this.setupWindowsJumpList();
  }

  /**
   * Set up Windows Jump List (right-click menu on taskbar icon)
   */
  private setupWindowsJumpList(): void {
    if (process.platform !== 'win32') return;

    app.setUserTasks([
      {
        program: process.execPath,
        arguments: '--show-logs',
        iconPath: process.execPath,
        iconIndex: 0,
        title: 'Logs',
        description: 'Open server logs',
      },
    ]);
  }

  /**
   * Check if app was launched with --show-logs argument
   */
  checkLaunchArgs(): void {
    if (process.argv.includes('--show-logs')) {
      // Delay to ensure window is ready
      setTimeout(() => {
        this.showLogsWindow();
      }, 1000);
    }
  }

  createMainWindow(): BrowserWindow {
    // Force dark mode for native UI elements (title bar, scrollbars, etc.)
    nativeTheme.themeSource = 'dark';

    // Determine preload path
    // With Electron Forge + Vite, preload.js is built to the same directory as main.js
    // In both dev and production, __dirname points to .vite/build/
    const preloadPath = path.join(__dirname, 'preload.js');

    // Determine icon path
    let iconPath: string;
    if (app.isPackaged) {
      iconPath = path.join(process.resourcesPath, 'app', 'assets', 'icon.png');
    } else {
      iconPath = path.join(__dirname, '../../assets/icon.png');
    }

    const icon = nativeImage.createFromPath(iconPath);
    const windowIcon = icon.isEmpty() ? undefined : icon;

    const mainWindow = new BrowserWindow({
      width: 1400,
      height: 900,
      title: 'Daydream Scope',
      icon: windowIcon,
      backgroundColor: '#0f0f0f', // Dark background to match theme
      titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'hidden', // Hidden title bar with overlay on Windows
      titleBarOverlay: process.platform === 'win32' ? {
        color: '#0f0f0f',
        symbolColor: '#ffffff',
        height: 32,
      } : undefined,
      autoHideMenuBar: true, // Hide menu bar (can still access with Alt key)
      webPreferences: {
        preload: preloadPath,
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: false, // Disabled because we need Node.js APIs in preload for IPC
        webSecurity: true,
        allowRunningInsecureContent: false,
        experimentalFeatures: false,
      },
      show: false, // Don't show until ready
    });

    // Security: Prevent navigation to external URLs
    mainWindow.webContents.on('will-navigate', (event, navigationUrl) => {
      try {
        const parsedUrl = new URL(navigationUrl);
        const allowedHosts = ['127.0.0.1', 'localhost', SERVER_CONFIG.host];

        if (!allowedHosts.includes(parsedUrl.hostname)) {
          event.preventDefault();
          logger.warn(`Blocked navigation to external URL: ${navigationUrl}`);
        }
      } catch (err) {
        // Invalid URL, prevent navigation
        event.preventDefault();
        logger.warn(`Blocked navigation to invalid URL: ${navigationUrl}`);
      }
    });

    // Security: Prevent new window creation (open external links)
    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
      try {
        const parsedUrl = new URL(url);
        const allowedHosts = ['127.0.0.1', 'localhost', SERVER_CONFIG.host];

        if (!allowedHosts.includes(parsedUrl.hostname)) {
          logger.warn(`Blocked new window to external URL: ${url}`);
          return { action: 'deny' };
        }

        return { action: 'allow' };
      } catch (err) {
        // Invalid URL, deny
        logger.warn(`Blocked new window to invalid URL: ${url}`);
        return { action: 'deny' };
      }
    });

    // Load the Electron renderer (setup screen) initially
    // The main process will check server status and load frontend if needed
    if (app.isPackaged) {
      // In production, load from the built renderer
      const indexPath = path.join(process.resourcesPath, 'app', '.vite', 'build', 'renderer', 'index.html');
      logger.info(`Loading from file: ${indexPath}`);
      mainWindow.loadFile(indexPath);
    } else {
      // In development, load from Vite dev server for renderer
      const devUrl = 'http://localhost:5173';
      logger.info(`Loading from dev server: ${devUrl}`);
      mainWindow.loadURL(devUrl).catch((err) => {
        logger.error(`Failed to load ${devUrl}:`, err);
      });
    }

    mainWindow.once('ready-to-show', () => {
      logger.info('Window ready to show');
      mainWindow.show();
    });

    // Add event listeners for debugging
    mainWindow.webContents.on('did-start-loading', () => {
      logger.info('Window started loading');
    });

    mainWindow.webContents.on('did-finish-load', () => {
      logger.info('Window finished loading');
    });

    mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription) => {
      logger.error(`Window failed to load: ${errorCode} - ${errorDescription}`);
    });

    mainWindow.on('closed', () => {
      this.appState.mainWindow = null;
    });

    // Add right-click context menu for the title bar area
    // This creates an app-level menu that appears on right-click in the title bar region
    this.setupWindowContextMenu(mainWindow);

    this.appState.mainWindow = mainWindow;
    return mainWindow;
  }

  private setupWindowContextMenu(_window: BrowserWindow): void {
    // Set up the application menu with context menu items (including keyboard shortcuts)
    const menu = Menu.buildFromTemplate([
      {
        label: 'File',
        submenu: [
          {
            label: 'Logs',
            accelerator: 'CmdOrCtrl+Shift+L',
            click: () => {
              this.showLogsWindow();
            },
          },
          { type: 'separator' },
          {
            label: 'Quit',
            accelerator: process.platform === 'darwin' ? 'Cmd+Q' : 'Alt+F4',
            click: () => {
              app.quit();
            },
          },
        ],
      },
    ]);

    // Set this as the application menu (accessible via Alt key)
    Menu.setApplicationMenu(menu);

    // Register global shortcut for logs (works even when menu is hidden)
    globalShortcut.register('CmdOrCtrl+Shift+L', () => {
      this.showLogsWindow();
    });
  }

  loadFrontend(): void {
    if (this.appState.mainWindow && !this.appState.mainWindow.isDestroyed()) {
      try {
        // Once server is running, load the actual frontend from Python server
        this.appState.mainWindow.loadURL(SERVER_CONFIG.url);
      } catch (err) {
        logger.error('Failed to load frontend:', err);
      }
    }
  }

  createTray(): void {
    // Create a simple tray icon
    let iconPath: string;
    if (app.isPackaged) {
      // Try tray-icon.png first, fall back to icon.png
      const trayIconPath = path.join(process.resourcesPath, 'app', 'assets', 'tray-icon.png');
      const fallbackIconPath = path.join(process.resourcesPath, 'app', 'assets', 'icon.png');
      iconPath = fs.existsSync(trayIconPath) ? trayIconPath : fallbackIconPath;
    } else {
      // Try tray-icon.png first, fall back to icon.png
      const trayIconPath = path.join(__dirname, '../../assets/tray-icon.png');
      const fallbackIconPath = path.join(__dirname, '../../assets/icon.png');
      iconPath = fs.existsSync(trayIconPath) ? trayIconPath : fallbackIconPath;
    }

    const icon = nativeImage.createFromPath(iconPath);
    this.tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon);

    const contextMenu = Menu.buildFromTemplate([
      {
        label: 'Show Window',
        click: () => {
          if (this.appState.mainWindow) {
            this.appState.mainWindow.show();
          }
        },
      },
      {
        label: 'Logs',
        click: () => {
          this.showLogsWindow();
        },
      },
      { type: 'separator' },
      {
        label: 'Quit',
        click: () => {
          app.quit();
        },
      },
    ]);

    this.tray.setToolTip('Daydream Scope');
    this.tray.setContextMenu(contextMenu);

    this.tray.on('click', () => {
      if (this.appState.mainWindow) {
        this.appState.mainWindow.show();
      }
    });
  }

  sendSetupStatus(status: string): void {
    if (this.appState.mainWindow && !this.appState.mainWindow.isDestroyed()) {
      try {
        this.appState.mainWindow.webContents.send(IPC_CHANNELS.SETUP_STATUS, status);
      } catch (err) {
        logger.error('Failed to send setup status:', err);
      }
    }
  }

  sendServerStatus(isRunning: boolean): void {
    if (this.appState.mainWindow && !this.appState.mainWindow.isDestroyed()) {
      try {
        this.appState.mainWindow.webContents.send(IPC_CHANNELS.SERVER_STATUS, isRunning);
      } catch (err) {
        logger.error('Failed to send server status:', err);
      }
    }
  }

  sendServerError(error: string): void {
    if (this.appState.mainWindow && !this.appState.mainWindow.isDestroyed()) {
      try {
        this.appState.mainWindow.webContents.send(IPC_CHANNELS.SERVER_ERROR, error);
      } catch (err) {
        logger.error('Failed to send server error:', err);
      }
    }
  }

  waitForMainWindowLoad(): Promise<void> {
    return new Promise((resolve) => {
      if (!this.appState.mainWindow) {
        resolve();
        return;
      }

      // Add timeout to prevent hanging forever
      const timeout = setTimeout(() => {
        logger.warn('Window load timeout, proceeding anyway');
        resolve();
      }, 10000); // 10 second timeout

      // Check if already loaded
      if (this.appState.mainWindow.webContents.isLoading() === false) {
        clearTimeout(timeout);
        resolve();
        return;
      }

      this.appState.mainWindow.webContents.once('did-finish-load', () => {
        clearTimeout(timeout);
        resolve();
      });

      // Also handle navigation failures
      this.appState.mainWindow.webContents.once('did-fail-load', () => {
        clearTimeout(timeout);
        logger.warn('Window failed to load, proceeding anyway');
        resolve();
      });
    });
  }

  cleanup(): void {
    // Unregister global shortcuts
    globalShortcut.unregisterAll();

    if (this.tray) {
      this.tray.destroy();
      this.tray = null;
    }
    if (this.logsWindow) {
      this.logsWindow.close();
      this.logsWindow = null;
    }
  }

  showContextMenu(): void {
    const contextMenu = Menu.buildFromTemplate([
      {
        label: 'Logs',
        click: () => {
          this.showLogsWindow();
        },
      },
      { type: 'separator' },
      {
        label: 'Quit',
        click: () => {
          app.quit();
        },
      },
    ]);

    contextMenu.popup();
  }

  showLogsWindow(): void {
    // If logs window already exists, focus it
    if (this.logsWindow && !this.logsWindow.isDestroyed()) {
      this.logsWindow.focus();
      return;
    }

    const logPath = getLogPath();

    // Create logs viewer window
    this.logsWindow = new BrowserWindow({
      width: 900,
      height: 600,
      title: 'Server Logs',
      backgroundColor: '#1a1a1a',
      autoHideMenuBar: true,
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
      },
    });

    // Read log file and display it
    let logContent = '';
    try {
      if (fs.existsSync(logPath)) {
        logContent = fs.readFileSync(logPath, 'utf-8');
        // Get the last 500 lines for better performance
        const lines = logContent.split('\n');
        if (lines.length > 500) {
          logContent = lines.slice(-500).join('\n');
        }
      } else {
        logContent = 'No logs found.';
      }
    } catch (err) {
      logContent = `Error reading logs: ${err}`;
    }

    // Escape HTML entities for safe display
    const escapedContent = logContent
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');

    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <meta charset="UTF-8">
          <title>Server Logs</title>
          <style>
            * {
              margin: 0;
              padding: 0;
              box-sizing: border-box;
            }
            body {
              font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
              background-color: #0f0f0f;
              color: #e0e0e0;
              padding: 16px;
              overflow: auto;
            }
            .header {
              position: sticky;
              top: -16px;
              background: #0f0f0f;
              padding: 12px 0;
              margin-bottom: 12px;
              border-bottom: 1px solid #333;
              display: flex;
              justify-content: space-between;
              align-items: center;
            }
            .header h1 {
              font-size: 18px;
              font-weight: 600;
              color: #fff;
            }
            .header button {
              background: #2a2a2a;
              border: 1px solid #444;
              color: #e0e0e0;
              padding: 8px 16px;
              border-radius: 4px;
              cursor: pointer;
              font-size: 13px;
            }
            .header button:hover {
              background: #3a3a3a;
            }
            .log-path {
              font-size: 11px;
              color: #888;
              margin-bottom: 16px;
            }
            pre {
              font-size: 12px;
              line-height: 1.5;
              white-space: pre-wrap;
              word-wrap: break-word;
            }
            .info { color: #4fc3f7; }
            .error { color: #ef5350; }
            .warn { color: #ffb74d; }
            .server { color: #81c784; }
          </style>
        </head>
        <body>
          <div class="header">
            <h1>Server Logs</h1>
            <button onclick="location.reload()">Refresh</button>
          </div>
          <div class="log-path">Log file: ${logPath.replace(/\\/g, '\\\\')}</div>
          <pre id="logs">${escapedContent}</pre>
          <script>
            // Scroll to bottom
            window.scrollTo(0, document.body.scrollHeight);

            // Apply syntax highlighting
            const pre = document.getElementById('logs');
            let html = pre.innerHTML;
            html = html.replace(/\\[INFO\\]/g, '<span class="info">[INFO]</span>');
            html = html.replace(/\\[ERROR\\]/g, '<span class="error">[ERROR]</span>');
            html = html.replace(/\\[WARN\\]/g, '<span class="warn">[WARN]</span>');
            html = html.replace(/\\[SERVER\\]/g, '<span class="server">[SERVER]</span>');
            pre.innerHTML = html;
          </script>
        </body>
      </html>
    `;

    this.logsWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(htmlContent)}`);

    this.logsWindow.on('closed', () => {
      this.logsWindow = null;
    });
  }

  getLogs(): string {
    const logPath = getLogPath();
    try {
      if (fs.existsSync(logPath)) {
        const content = fs.readFileSync(logPath, 'utf-8');
        // Return last 500 lines
        const lines = content.split('\n');
        if (lines.length > 500) {
          return lines.slice(-500).join('\n');
        }
        return content;
      }
      return 'No logs found.';
    } catch (err) {
      return `Error reading logs: ${err}`;
    }
  }
}
