import org.tio.client.ClientChannelContext;
import org.tio.client.TioClient;
import org.tio.client.TioClientConfig;
import org.tio.client.intf.TioClientHandler;
import org.tio.client.intf.TioClientListener;
import org.tio.core.ChannelContext;
import org.tio.core.Tio;
import org.tio.core.TioConfig;
import org.tio.core.exception.TioDecodeException;
import org.tio.core.intf.Packet;
import org.tio.core.Node;

import java.io.IOException;
import java.nio.ByteBuffer;

public class Client {
    public static Node serverNode = new Node("127.0.0.1", 6789);
    private static HelloPacket heartbeatPacket = new HelloPacket();
    private static TioClientListener tioClientListener = new TioClientListener() {
        @Override
        public void onAfterConnected(ChannelContext channelContext, boolean b, boolean b1) throws Exception {
            System.out.println("onAfterConnected");
        }

        @Override
        public void onAfterDecoded(ChannelContext channelContext, Packet packet, int i) throws Exception {
            System.out.println("onAfterDecoded");
        }

        @Override
        public void onAfterReceivedBytes(ChannelContext channelContext, int i) throws Exception {
            System.out.println("onAfterReceivedBytes");
        }

        @Override
        public void onAfterSent(ChannelContext channelContext, Packet packet, boolean b) throws Exception {
            System.out.println("onAfterSent");
        }

        @Override
        public void onAfterHandled(ChannelContext channelContext, Packet packet, long l) throws Exception {
            System.out.println("onAfterHandled");
        }

        @Override
        public void onBeforeClose(ChannelContext channelContext, Throwable throwable, String s, boolean b) throws Exception {
            System.out.println("onBeforeClose");
        }
    };
    private static TioClientHandler tioClientHandler = new TioClientHandler() {
        @Override
        public Packet heartbeatPacket(ChannelContext channelContext) {
            System.out.println("heartbeatPacket");
            return heartbeatPacket;
        }

        @Override
        public Packet decode(ByteBuffer byteBuffer, int i, int i1, int i2, ChannelContext channelContext) throws TioDecodeException {
            return null;
        }

        @Override
        public ByteBuffer encode(Packet packet, TioConfig tioConfig, ChannelContext channelContext) {
            return null;
        }

        @Override
        public void handler(Packet packet, ChannelContext channelContext) throws Exception {
            byte[] body = packet.getPreEncodedByteBuffer().array();
            if (body != null)
            {
                String str = new String(body, HelloPacket.CHARSET);
                System.out.println("收到消息：" + str);
            }
        }
    };
    private static TioClientConfig tioClientConfig = new TioClientConfig(tioClientHandler, tioClientListener);


    public static void main(String[] args) {
        try {
            TioClient client = new TioClient(tioClientConfig);
            ClientChannelContext clientChannelContext = client.connect(serverNode);

            HelloPacket packet = new HelloPacket();
            packet.setBody("hello world".getBytes(HelloPacket.CHARSET));
            Tio.send(clientChannelContext, packet);
        }
        catch (IOException e) {
            System.out.println(e.getMessage());
        }
        catch (Exception e) {
            System.out.println(e.getMessage());
        }
    }
}
