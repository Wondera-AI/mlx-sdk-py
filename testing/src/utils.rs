use anyhow::Result;
use pyo3::prelude::*;
use pyo3::types::{PyModule, PyTuple};
use std::fs;
use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use std::thread;
use tracing::{debug, error, info};

#[macro_export]
macro_rules! run_tests {
    ($( $test:expr ),*) => {
        {
            let mut all_passed = true;
            let tests: Vec<(&str, fn() -> Result<(), Box<dyn std::error::Error>>)> = vec![
                $(
                    (stringify!($test), $test as fn() -> Result<(), Box<dyn std::error::Error>>)
                ),*
            ];

            for (i, (name, test)) in tests.iter().enumerate() {
                println!("=== Running Test #{}: {} ===", i + 1, name);
                if let Err(err) = test() {
                    error!("Test #{}: {} failed with error: {}", i + 1, name, err);
                    all_passed = false;
                }
            }

            if all_passed {
                info!("All tests passed successfully.");
                std::process::exit(0);
            } else {
                std::process::exit(1);
            }
        }
    };
}

pub fn run_python_script(file_path: &str, args: &[&str]) -> Result<()> {
    debug!("Running Python script: {} with args: {:?}", file_path, args);

    let mut child_process = Command::new("python3")
        .arg("-u")
        .arg(file_path)
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;

    let stdout = child_process.stdout.take().unwrap();
    let stderr = child_process.stderr.take().unwrap();

    let stdout_thread = thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            debug!("stdout: {}", line.unwrap());
        }
    });

    let stderr_thread = thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines() {
            debug!("stderr: {}", line.unwrap());
        }
    });

    stdout_thread.join().unwrap();
    stderr_thread.join().unwrap();

    let output = child_process.wait()?;
    if output.success() {
        info!("Script executed successfully.");
        Ok(())
    } else {
        error!("Python script failed with exit code: {}", output);
        Err(anyhow::anyhow!("Script failed"))
    }
}

pub fn call_python_function<I, O>(file_path: &str, function_name: &str, input_data: I) -> Result<O>
where
    I: ToPyObject,
    // I: IntoPy<Py<PyTuple>>,
    O: for<'a> FromPyObject<'a>,
{
    info!(
        "Calling Python function '{}' from file '{}'",
        function_name, file_path
    );

    let python_code = fs::read_to_string(file_path)?;
    let module_name = file_path.split('/').last().unwrap_or("module");

    Python::with_gil(|py| -> Result<O> {
        let module = PyModule::from_code_bound(py, &python_code, file_path, module_name)?;

        let binding = input_data.to_object(py);
        let py_args = if let Ok(py_tuple) = binding.downcast_bound::<PyTuple>(py) {
            py_tuple
        } else {
            &PyTuple::new_bound(py, &[input_data.to_object(py)])
        };

        let result = module
            .getattr(function_name)?
            .call1(py_args)?
            .extract::<O>()?;

        Ok(result)
    })
}
