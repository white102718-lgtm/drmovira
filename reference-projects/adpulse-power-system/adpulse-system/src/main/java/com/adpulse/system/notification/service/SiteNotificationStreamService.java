package com.adpulse.system.notification.service;

import com.adpulse.system.auth.service.SessionStore;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.notification.dto.SiteNotificationEvent;
import com.adpulse.system.notification.mapper.SystemNotificationMapper;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.io.IOException;
import java.time.Duration;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CopyOnWriteArraySet;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/** 管理当前 system 实例上的站内通知 SSE 连接、断线补发与心跳。 */
@Service
public class SiteNotificationStreamService {
    private static final Logger LOGGER =
            LoggerFactory.getLogger(SiteNotificationStreamService.class);
    private static final int REPLAY_BATCH_SIZE = 100;
    private static final Duration HEARTBEAT_INTERVAL = Duration.ofSeconds(25);

    private final SystemNotificationMapper mapper;
    private final SessionStore sessionStore;
    private final ConcurrentMap<Long, CopyOnWriteArraySet<StreamConnection>> connections =
            new ConcurrentHashMap<>();
    private final ScheduledExecutorService heartbeatExecutor =
            Executors.newSingleThreadScheduledExecutor(
                    runnable -> {
                        Thread thread = new Thread(runnable, "site-notification-sse-heartbeat");
                        thread.setDaemon(true);
                        return thread;
                    });

    public SiteNotificationStreamService(
            SystemNotificationMapper mapper, SessionStore sessionStore) {
        this.mapper = mapper;
        this.sessionStore = sessionStore;
    }

    @PostConstruct
    void startHeartbeat() {
        heartbeatExecutor.scheduleAtFixedRate(
                this::heartbeatAll,
                HEARTBEAT_INTERVAL.toSeconds(),
                HEARTBEAT_INTERVAL.toSeconds(),
                TimeUnit.SECONDS);
    }

    /** 建立连接；仅在客户端提供 Last-Event-ID 时补发该游标之后的通知。 */
    public SseEmitter subscribe(CurrentUser user, Long lastEventId) {
        SseEmitter emitter = new SseEmitter(0L);
        StreamConnection connection =
                new StreamConnection(user.userId(), user.sessionId(), emitter);
        connections
                .computeIfAbsent(user.userId(), ignored -> new CopyOnWriteArraySet<>())
                .add(connection);
        emitter.onCompletion(() -> remove(connection));
        emitter.onTimeout(() -> remove(connection));
        emitter.onError(ignored -> remove(connection));

        try {
            long cursor = lastEventId == null ? latestNotificationId(user.userId()) : lastEventId;
            connection.sendConnected(cursor);
            if (lastEventId != null) replay(connection, cursor);
            connection.discardPendingThrough(cursor);
            connection.finishReplay();
        } catch (RuntimeException | IOException exception) {
            remove(connection);
            emitter.completeWithError(exception);
        }
        return emitter;
    }

    private long latestNotificationId(Long userId) {
        Long latestId = mapper.findLatestNotificationId(userId);
        return latestId == null ? 0 : latestId;
    }

    /** 接收 Redis 广播，并定向发送给该用户在本实例上的全部连接。 */
    public void deliver(Long userId, SiteNotificationEvent notification) {
        CopyOnWriteArraySet<StreamConnection> userConnections = connections.get(userId);
        if (userConnections == null) return;
        for (StreamConnection connection : userConnections) {
            try {
                connection.accept(notification);
            } catch (RuntimeException | IOException exception) {
                remove(connection);
                connection.emitter().completeWithError(exception);
            }
        }
    }

    private void replay(StreamConnection connection, Long lastEventId) throws IOException {
        long cursor = lastEventId;
        while (true) {
            List<SiteNotificationEvent> notifications =
                    mapper
                            .findNotificationsAfter(connection.userId(), cursor, REPLAY_BATCH_SIZE)
                            .stream()
                            .map(SiteNotificationEvent::from)
                            .toList();
            if (notifications.isEmpty()) return;
            for (SiteNotificationEvent notification : notifications) {
                connection.sendReplay(notification);
                cursor = Long.parseLong(notification.id());
            }
            if (notifications.size() < REPLAY_BATCH_SIZE) return;
        }
    }

    private void heartbeatAll() {
        try {
            for (CopyOnWriteArraySet<StreamConnection> userConnections : connections.values()) {
                for (StreamConnection connection : userConnections) heartbeat(connection);
            }
        } catch (RuntimeException exception) {
            LOGGER.warn("站内通知 SSE 心跳任务执行失败", exception);
        }
    }

    private void heartbeat(StreamConnection connection) {
        try {
            if (sessionStore.find(connection.sessionId()).isEmpty()) {
                remove(connection);
                connection.emitter().complete();
                return;
            }
            connection.sendHeartbeat();
        } catch (RuntimeException | IOException exception) {
            remove(connection);
            connection.emitter().completeWithError(exception);
        }
    }

    private void remove(StreamConnection connection) {
        CopyOnWriteArraySet<StreamConnection> userConnections =
                connections.get(connection.userId());
        if (userConnections == null) return;
        userConnections.remove(connection);
        if (userConnections.isEmpty()) connections.remove(connection.userId(), userConnections);
    }

    @PreDestroy
    void shutdown() {
        heartbeatExecutor.shutdownNow();
        for (CopyOnWriteArraySet<StreamConnection> userConnections : connections.values()) {
            userConnections.forEach(connection -> connection.emitter().complete());
        }
        connections.clear();
    }

    /** 单连接写入必须串行化；重放期间到达的实时事件先排队，避免游标跨越造成漏发。 */
    private static final class StreamConnection {
        private final Long userId;
        private final String sessionId;
        private final SseEmitter emitter;
        private final Map<Long, SiteNotificationEvent> pendingEvents = new ConcurrentHashMap<>();
        private boolean replaying = true;

        private StreamConnection(Long userId, String sessionId, SseEmitter emitter) {
            this.userId = userId;
            this.sessionId = sessionId;
            this.emitter = emitter;
        }

        private Long userId() {
            return userId;
        }

        private String sessionId() {
            return sessionId;
        }

        private SseEmitter emitter() {
            return emitter;
        }

        private synchronized void sendConnected(long cursor) throws IOException {
            emitter.send(
                    SseEmitter.event()
                            .id(Long.toString(cursor))
                            .name("connected")
                            .reconnectTime(1_000)
                            .data("{}"));
        }

        private synchronized void accept(SiteNotificationEvent notification) throws IOException {
            if (replaying) {
                pendingEvents.put(Long.parseLong(notification.id()), notification);
                return;
            }
            send(notification);
        }

        private synchronized void sendReplay(SiteNotificationEvent notification)
                throws IOException {
            send(notification);
            pendingEvents.remove(Long.parseLong(notification.id()));
        }

        private synchronized void discardPendingThrough(long cursor) {
            pendingEvents.keySet().removeIf(id -> id <= cursor);
        }

        private synchronized void finishReplay() throws IOException {
            replaying = false;
            List<SiteNotificationEvent> pending =
                    pendingEvents.values().stream()
                            .sorted(Comparator.comparingLong(item -> Long.parseLong(item.id())))
                            .toList();
            pendingEvents.clear();
            for (SiteNotificationEvent notification : pending) send(notification);
        }

        private synchronized void sendHeartbeat() throws IOException {
            emitter.send(SseEmitter.event().comment("heartbeat"));
        }

        private void send(SiteNotificationEvent notification) throws IOException {
            emitter.send(
                    SseEmitter.event()
                            .id(notification.id())
                            .name("notification")
                            .data(notification));
        }
    }
}
