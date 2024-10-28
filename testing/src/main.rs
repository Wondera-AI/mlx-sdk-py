mod utils;
use futures_util::stream::StreamExt;
use redis::{aio::MultiplexedConnection, AsyncCommands, Client, RedisError};
use tokio;
use tokio::time::{timeout, Duration};
use tracing::{error, info};
use tracing_subscriber::{filter::EnvFilter, fmt, layer::SubscriberExt, util::SubscriberInitExt};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::registry()
        .with(fmt::layer().with_writer(std::io::stdout))
        .with(EnvFilter::new(
            std::env::var("RUST_LOG").unwrap_or_else(|_| "debug".into()),
        ))
        .init();

    pyo3::prepare_freethreaded_python();

    run_tests!(
        // test_run_python_script,
        // test_call_python_function,
        test_sdk_main
    );
}

static SCRIPT_PATH: &str = "./testing/userland_service.py";
static TIMEOUT: Duration = Duration::from_secs(5);

static MESSAGE_B: &str = r#"
{
    "request_data": "{\"body\": {\"foo\": \"message B\"}}",
    "response_channel": "service-test-1-service_b-output",
    "log_key": "service-test-1-service_b-log"
}
"#;

static MESSAGE_A: &str = r#"
{
    "request_data": "{\"body\": {\"foo\": \"message A\"}}",
    "response_channel": "service-test-1-service_a-output",
    "log_key": "service-test-1-service_a-log"
}
"#;

#[tokio::main]
async fn test_sdk_main() -> Result<(), Box<dyn std::error::Error>> {
    let client = redis::Client::open("redis://:MkiTVpOWFVLGLgJ7ptZ29dY80zER4cvR@redis-17902.c322.us-east-1-2.ec2.redns.redis-cloud.com:17902")?;
    let mut conn = client.get_multiplexed_async_connection().await?;
    let log_key_a = "service-test-1-service_a-log";
    let log_key_b = "service-test-1-service_b-log";
    _clean_test_env(conn.clone(), &[log_key_a, log_key_b]).await?;

    info!("Starting service B");
    let args_b = ["service_b", r#"{"smoothing": 1}"#];
    let publish_channel_b = "service-test-1-service_b";
    let response_channel_b = "service-test-1-service_b-output";
    let expected_response = r#"{"bar":"message B"}"#;

    let _ = tokio::spawn(async move {
        utils::run_python_script(SCRIPT_PATH, &args_b).expect("Failed to run script");
    });

    info!("Starting service A");
    let args_a = ["service_a", r#"{"smoothing": 1}"#];
    let publish_channel_a = "service-test-1-service_a";
    let response_channel_a = "service-test-1-service_a-output";
    let expected_response_a = r#"{"bar":"message A"}"#;

    let _ = tokio::spawn(async move {
        utils::run_python_script(SCRIPT_PATH, &args_a).expect("Failed to run script");
    });

    tokio::time::sleep(std::time::Duration::from_secs(7)).await;

    info!("Publishing request to service B");
    conn.publish(publish_channel_b, MESSAGE_B).await?;
    let resp = _subscribe_and_wait_for_response(&client, &response_channel_b, TIMEOUT).await?;
    info!("Received response: \n {}", resp);
    assert_eq!(
        resp, expected_response,
        "The response did not match the expected output."
    );

    let logs: String = conn.hget(log_key_b, "logs").await?;
    info!("Logs: {}", logs);
    // assert_eq!(
    //     logs, expected_logs_b,
    //     "The logs did not match the expected logs."
    // );

    info!("Publishing request to service A");
    conn.publish(publish_channel_a, MESSAGE_A).await?;
    let resp = _subscribe_and_wait_for_response(&client, &response_channel_a, TIMEOUT).await?;
    info!("Received response: \n {}", resp);
    assert_eq!(
        resp, expected_response_a,
        "The response did not match the expected output."
    );

    let logs: String = conn.hget(log_key_a, "logs").await?;
    info!("Logs: {}", logs);
    // assert_eq!(
    //     logs, expected_logs_a,
    //     "The logs did not match the expected logs."
    // );

    conn.publish(publish_channel_b, "stop").await?;
    conn.publish(publish_channel_a, "stop").await?;
    drop(conn);

    Ok(())
}

async fn _subscribe_and_wait_for_response(
    client: &Client,
    subscribe_channel: &str,
    timeout_duration: Duration,
) -> Result<String, RedisError> {
    let mut conn = client.get_async_pubsub().await?;
    conn.subscribe(subscribe_channel).await?;

    let mut pubsub_stream = conn.on_message();
    let response = match timeout(timeout_duration, pubsub_stream.next()).await {
        Ok(Some(msg)) => {
            let payload: String = msg.get_payload()?;
            Ok(payload)
        }
        Ok(None) => Err(RedisError::from((
            redis::ErrorKind::IoError,
            "No message received",
        ))),
        Err(_) => Err(RedisError::from((
            redis::ErrorKind::IoError,
            "Timeout waiting for response",
        ))),
    };

    drop(pubsub_stream);
    conn.unsubscribe(subscribe_channel).await?;
    drop(conn);

    response
}

async fn _clean_test_env(
    mut conn: MultiplexedConnection,
    log_keys: &[&str],
) -> Result<(), RedisError> {
    info!("Setting up clean test environment");

    info!("Cleaning old Ray cluster");
    let ray_stop_output = std::process::Command::new("ray")
        .arg("stop")
        .arg("--force")
        .arg("--grace-period")
        .arg("30")
        .output()
        .expect("Failed to execute ray stop");

    if !ray_stop_output.status.success() {
        eprintln!(
            "Ray stop failed: {}",
            String::from_utf8_lossy(&ray_stop_output.stderr)
        );
    }

    info!("Clearing log key before test");
    for log_key in log_keys {
        conn.hset(log_key, "logs", "").await?;
    }

    Ok(())
}

// fn test_run_python_script() -> Result<(), Box<dyn std::error::Error>> {
//     let script_path = "./testing/example.py";
//     let args = ["service_b", r#"{"smoothing": 1}"#];
//     utils::run_python_script(script_path, &args)?;

//     Ok(())g
// }

// fn test_call_python_function() -> Result<(), Box<dyn std::error::Error>> {
//     let result: String =
//         utils::call_python_function("./testing/example.py", "string_function", "test_input")?;

//     info!("Function result: {}", result);
//     assert_eq!(result, "test_input_processed");

//     let result: i32 =
//         utils::call_python_function("./testing/example.py", "sum_function", (42, 42))?;

//     info!("Function result: {}", result);
//     assert_eq!(result, 84);

//     Ok(())
// }

// let expected_logs_b = "\
// Received request for 'service_b' with input: {'foo': 'message B'}\n\
// Inside Service B: foo='message B'\n\
// w/ Config B: smoothing=1.0\n\
// Service 'service_b' Output: {\"bar\":\"message B\"}\n";

// let expected_logs_a = "\
// Inside Service A: foo='message A'\n\
// Received request for 'service_a' with input: {'foo': 'message A'}\n\
// Remote call to service_b with input: {'foo': 'message A'}\n\
// Next service channel: service-test-1-service_b\n\
// w/ Config A: smoothing=1.0\n\
// Remote publish to service-test-1-service_b with msg: \n\
// {'request_data': '{\"body\": {\"foo\": \"message A\"}}', 'response_channel': '2fd9959aec42e035a017b52b7f2c5c76a8b51dc22096f60f72decfb2e94bbdc1', 'log_key': 'service-test-1-service_a-log'}\n\
// w/ Config B: smoothing=1.0\n\
// Received request for 'service_b' with input: {'foo': 'message A'}\n\
// Inside Service B: foo='message A'\n\
// Service 'service_b' Output: {\"bar\":\"message A\"}\n\
// Remote call response: {\"bar\":\"message A\"}\n\
// Response from B in Service A: {'bar': 'message A'}\n\
// Service 'service_a' Output: {\"bar\":\"message A\"}\n";
