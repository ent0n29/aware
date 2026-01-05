package com.polybot.hft.polymarket.fund;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.polybot.hft.config.HftProperties;
import com.polybot.hft.polymarket.api.LimitOrderRequest;
import com.polybot.hft.polymarket.api.OrderSubmissionResult;
import com.polybot.hft.polymarket.api.PolymarketAccountResponse;
import com.polybot.hft.polymarket.api.PolymarketBankrollResponse;
import com.polybot.hft.polymarket.data.PolymarketPosition;
import com.polybot.hft.strategy.executor.ExecutorApiClient;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

/**
 * Test stub for ExecutorApiClient to avoid Mockito issues with Java 25.
 */
public class MockExecutorApiClient extends ExecutorApiClient {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final List<LimitOrderRequest> submittedOrders = new ArrayList<>();
    private OrderSubmissionResult nextResult;
    private int orderCounter = 0;

    public MockExecutorApiClient() {
        super(null, null, null);
    }

    public void setNextResult(OrderSubmissionResult result) {
        this.nextResult = result;
    }

    @Override
    public OrderSubmissionResult placeLimitOrder(LimitOrderRequest request) {
        submittedOrders.add(request);
        if (nextResult != null) {
            return nextResult;
        }
        // Default response
        ObjectNode clobResponse = objectMapper.createObjectNode();
        clobResponse.put("orderID", "order-" + (++orderCounter));
        clobResponse.put("status", "LIVE");
        return new OrderSubmissionResult(HftProperties.TradingMode.PAPER, null, clobResponse);
    }

    @Override
    public BigDecimal getTickSize(String tokenId) {
        return BigDecimal.valueOf(0.01);
    }

    @Override
    public void cancelOrder(String orderId) {
        // No-op for tests
    }

    @Override
    public JsonNode getOrder(String orderId) {
        return objectMapper.createObjectNode();
    }

    @Override
    public PolymarketAccountResponse getAccount() {
        return null;
    }

    @Override
    public PolymarketBankrollResponse getBankroll() {
        return null;
    }

    @Override
    public PolymarketPosition[] getPositions(int limit, int offset) {
        return new PolymarketPosition[0];
    }

    @Override
    public PolymarketPosition[] getPositions(String user, int limit, int offset) {
        return new PolymarketPosition[0];
    }

    public List<LimitOrderRequest> getSubmittedOrders() {
        return submittedOrders;
    }

    public void reset() {
        submittedOrders.clear();
        nextResult = null;
        orderCounter = 0;
    }
}
