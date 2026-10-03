#!/bin/bash
# Ask-Along のクラウド側を AWS に作る・更新する(何度流してもよい)。
# 作るもの: S3 のバケット、IAM のロール、Lambda の関数2つ(on_upload / api)、関数 URL、S3 から Lambda への通知。
# on_upload は Rekognition の場面検出(1分 $0.05)と Bedrock の Nova Pro を呼ぶ。
# アカウントは 166690002196(Harbitt ではない方)、地域は us-east-1(Nova Pro の us. 推論プロファイルを使うため)。
# 注意: Lambda の同時実行数の上限が 10 のアカウントなので、予約の同時実行数(reserved concurrency)は設定しない。
set -euo pipefail
cd "$(dirname "$0")"

PROFILE=default
REGION=us-east-1
ACCOUNT=166690002196
BUCKET=askalong-${ACCOUNT}-use1
ROLE=askalong-lambda
FN_UPLOAD=askalong-on-upload
FN_API=askalong-api
AWS="aws --profile $PROFILE --region $REGION"

[ "$($AWS sts get-caller-identity --query Account --output text)" = "$ACCOUNT" ] || { echo "アカウントが違います"; exit 1; }

# --- S3(公開しない。動画は署名つき URL で渡す) ---
if ! $AWS s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  $AWS s3api create-bucket --bucket "$BUCKET"
  $AWS s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi

# --- IAM のロール ---
if ! $AWS iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  $AWS iam create-role --role-name "$ROLE" --assume-role-policy-document '{
    "Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  $AWS iam attach-role-policy --role-name "$ROLE" --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  sleep 10  # ロールが使えるようになるまで待つ
fi
$AWS iam put-role-policy --role-name "$ROLE" --policy-name askalong --policy-document "{
  \"Version\":\"2012-10-17\",\"Statement\":[
    {\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\"],\"Resource\":\"arn:aws:s3:::${BUCKET}/*\"},
    {\"Effect\":\"Allow\",\"Action\":\"s3:ListBucket\",\"Resource\":\"arn:aws:s3:::${BUCKET}\"},
    {\"Effect\":\"Allow\",\"Action\":[\"rekognition:StartSegmentDetection\",\"rekognition:GetSegmentDetection\"],\"Resource\":\"*\"},
    {\"Effect\":\"Allow\",\"Action\":\"bedrock:InvokeModel\",\"Resource\":[
      \"arn:aws:bedrock:*:${ACCOUNT}:inference-profile/us.amazon.nova-pro-v1:0\",
      \"arn:aws:bedrock:*::foundation-model/amazon.nova-pro-v1:0\"]}]}"
ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/${ROLE}"

# --- Lambda の zip(handler + questions + Linux arm64 用の ffmpeg を含む imageio-ffmpeg) ---
BUILD=$(mktemp -d)
cp handler.py questions.py "$BUILD/"
../tools/.venv/bin/pip install -q --target "$BUILD" --platform manylinux2014_aarch64 --only-binary=:all: \
  --python-version 3.12 --no-deps imageio-ffmpeg
chmod 755 "$BUILD"/imageio_ffmpeg/binaries/ffmpeg-*
(cd "$BUILD" && zip -q -r ../askalong.zip .)
ZIP="$BUILD/../askalong.zip"

deploy_fn() {  # 関数名 ハンドラ メモリ(MB) タイムアウト(秒)
  if $AWS lambda get-function --function-name "$1" >/dev/null 2>&1; then
    $AWS lambda update-function-code --function-name "$1" --zip-file "fileb://$ZIP" >/dev/null
    $AWS lambda wait function-updated --function-name "$1"
    $AWS lambda update-function-configuration --function-name "$1" --handler "$2" --memory-size "$3" \
      --timeout "$4" --environment "Variables={BUCKET=$BUCKET}" >/dev/null
  else
    $AWS lambda create-function --function-name "$1" --runtime python3.12 --architectures arm64 \
      --role "$ROLE_ARN" --handler "$2" --memory-size "$3" --timeout "$4" --ephemeral-storage Size=2048 \
      --environment "Variables={BUCKET=$BUCKET}" --zip-file "fileb://$ZIP" >/dev/null
  fi
  $AWS lambda wait function-updated --function-name "$1"
}
deploy_fn "$FN_UPLOAD" handler.on_upload 2048 900
deploy_fn "$FN_API" handler.api 256 30
rm -rf "$BUILD" "$ZIP"

# 失敗しても自動でやり直さない(やり直すと Rekognition と Nova の費用が3倍になった。2026-10-03)
$AWS lambda put-function-event-invoke-config --function-name "$FN_UPLOAD" --maximum-retry-attempts 0 >/dev/null

# --- S3 に動画が置かれたら on_upload を動かす ---
$AWS lambda add-permission --function-name "$FN_UPLOAD" --statement-id s3-invoke --action lambda:InvokeFunction \
  --principal s3.amazonaws.com --source-arn "arn:aws:s3:::${BUCKET}" --source-account "$ACCOUNT" >/dev/null 2>&1 || true
$AWS s3api put-bucket-notification-configuration --bucket "$BUCKET" --notification-configuration "{
  \"LambdaFunctionConfigurations\":[{\"LambdaFunctionArn\":\"arn:aws:lambda:${REGION}:${ACCOUNT}:function:${FN_UPLOAD}\",
  \"Events\":[\"s3:ObjectCreated:*\"],\"Filter\":{\"Key\":{\"FilterRules\":[{\"Name\":\"prefix\",\"Value\":\"videos/\"}]}}}]}"

# --- テレビのアプリが呼ぶ関数 URL(読み取りだけ。認証なし。返すのは CC の作品の一覧と質問だけ) ---
if ! $AWS lambda get-function-url-config --function-name "$FN_API" >/dev/null 2>&1; then
  $AWS lambda create-function-url-config --function-name "$FN_API" --auth-type NONE >/dev/null
  $AWS lambda add-permission --function-name "$FN_API" --statement-id public-url --action lambda:InvokeFunctionUrl \
    --principal '*' --function-url-auth-type NONE >/dev/null
  # 2025年10月から、関数 URL には lambda:InvokeFunction の許可も要る(Lambda 文書 urls-auth)。
  # 手元の aws CLI には --invoked-via-function-url が無いので boto3 で付ける。関数 URL 経由の呼び出しだけに限る。
  ../tools/.venv/bin/python -c "import boto3; boto3.Session(profile_name='$PROFILE').client('lambda', region_name='$REGION').add_permission(FunctionName='$FN_API', StatementId='public-url-invoke', Action='lambda:InvokeFunction', Principal='*', InvokedViaFunctionUrl=True)"
fi
echo "API: $($AWS lambda get-function-url-config --function-name "$FN_API" --query FunctionUrl --output text)"
